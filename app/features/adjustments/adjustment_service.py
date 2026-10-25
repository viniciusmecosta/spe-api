from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainException
from app.database.unit_of_work import transactional, unit_of_work
from app.features.adjustments.adjustment_actions import adjustment_action
from app.features.adjustments.adjustment_exceptions import (
    AdjustmentAttachmentNotFoundError,
    AdjustmentNotFoundError,
    AdjustmentPermissionError,
    AttachmentFileNotFoundError,
    CorruptedAttachmentError,
    InvalidAdjustmentFilenameError,
    InvalidAdjustmentTypeError,
    InvalidAttachmentFormatError,
    WaiverAttachmentRequiredError,
    WaiverLimitExceededError,
)
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.adjustments.adjustment_repository import (
    AsyncAdjustmentRepository,
    async_adjustment_repository,
)
from app.features.adjustments.adjustment_schemas import (
    AdjustmentRequestCreate,
    AdjustmentWaiverCreate,
)
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service, serialize_model
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import AdjustmentStatus, AdjustmentType, UserRole
from app.shared.storage import resolve_stored_file
from app.shared.timezone import local_day_bounds, to_app_timezone
from app.shared.upload_storage import UploadCategory, upload_storage

NOT_FOUND_MSG = "Solicitação não encontrada."


class AdjustmentService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None,
            repo: Annotated[AsyncAdjustmentRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncAdjustmentRepository:
        return self._repo if self._repo is not None else async_adjustment_repository

    @repo.setter
    def repo(self, value: AsyncAdjustmentRepository) -> None:
        self._repo = value

    async def _enrich_adjustments_with_records(self, db: AsyncSession, adjustments: list[AdjustmentRequest]) -> list[
        AdjustmentRequest]:
        if not adjustments:
            return []

        user_ids = {a.user_id for a in adjustments}
        min_date = min(a.target_date for a in adjustments)
        max_date = max(a.target_date for a in adjustments)

        min_dt, _ = local_day_bounds(min_date)
        _, max_dt = local_day_bounds(max_date)

        stmt = select(TimeRecord).where(
            TimeRecord.user_id.in_(user_ids),
            TimeRecord.record_datetime >= min_dt,
            TimeRecord.record_datetime < max_dt,
            TimeRecord.is_ignored.is_(False),
        ).order_by(TimeRecord.record_datetime.asc())
        result = await db.scalars(stmt)
        records = result.all()

        for adj in adjustments:
            adj.time_records = [
                r for r in records
                if r.user_id == adj.user_id
                and to_app_timezone(r.record_datetime).date() == adj.target_date
            ]

        return adjustments

    async def _validate_waiver_limit(self, db: AsyncSession, user_id: int, target_date: date,
                                     amount_hours: float | None):
        import math
        if amount_hours is None or not math.isfinite(amount_hours) or amount_hours <= 0:
            raise WaiverLimitExceededError("O abono deve informar uma quantidade positiva e finita de horas.")
        await self.repo.lock_waivers(db, user_id, target_date)

        existing_waivers = await self.repo.get_waivers_by_user_and_date(db, user_id, target_date)
        existing_hours = sum(w.amount_hours for w in existing_waivers if w.amount_hours)

        if existing_hours + amount_hours > 10.0:
            remaining = max(0.0, 10.0 - existing_hours)
            raise WaiverLimitExceededError(
                f"Limite máximo de 10 horas de abono por dia excedido. Horas disponíveis para esta data: {remaining}h."
            )

    async def _validate_period_open(self, session: AsyncSession, target_date: date) -> None:
        if hasattr(payroll_service, "async_validate_period_open"):
            await payroll_service.async_validate_period_open(session, target_date)
        else:
            payroll_service.validate_period_open(session, target_date)

    async def get_all_enriched(
            self, db: AsyncSession | None = None, skip: int = 0, limit: int = 100,
            month: int | None = None, year: int | None = None,
            status: str | None = None,
            order_by: str = "created_at", order_direction: str = "desc"
    ) -> list[AdjustmentRequest]:
        session = db if db is not None else self.db
        assert session is not None
        adjustments = await self.repo.get_all(session, skip, limit, month, year, status, order_by, order_direction)
        return await self._enrich_adjustments_with_records(session, adjustments)

    async def get_my_enriched(
            self, db: AsyncSession | None = None, user_id: int = 0, skip: int = 0, limit: int = 100,
            month: int | None = None, year: int | None = None,
            status: str | None = None,
            order_by: str = "created_at", order_direction: str = "desc"
    ) -> list[AdjustmentRequest]:
        session = db if db is not None else self.db
        assert session is not None
        adjustments = await self.repo.get_all_by_user(session, user_id, skip, limit, month, year, status, order_by,
                                                            order_direction)
        return await self._enrich_adjustments_with_records(session, adjustments)

    @transactional
    async def create_adjustment_request(self, db: AsyncSession | None = None, user_id: int = 0,
                                  obj_in: AdjustmentRequestCreate | None = None) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        await self._validate_period_open(session, obj_in.target_date)

        if obj_in.adjustment_type == AdjustmentType.EXTRA_TIME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hora extra manual foi descontinuada. O excedente é calculado automaticamente."
            )

        if obj_in.adjustment_type == AdjustmentType.WAIVER:
            await self._validate_waiver_limit(session, user_id, obj_in.target_date, obj_in.amount_hours)

        adjustment = await self.repo.create(session, user_id=user_id, obj_in=obj_in)
        enriched = await self._enrich_adjustments_with_records(session, [adjustment])
        return enriched[0]

    @transactional
    async def create_manager_waiver(self, db: AsyncSession | None = None,
                                    waiver_in: AdjustmentWaiverCreate | None = None,
                              manager_id: int = 0) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        assert waiver_in is not None
        await self._validate_period_open(session, waiver_in.target_date)
        await self._validate_waiver_limit(session, waiver_in.user_id, waiver_in.target_date, waiver_in.amount_hours)

        adj_in = AdjustmentRequestCreate(
            adjustment_type=AdjustmentType.WAIVER,
            target_date=waiver_in.target_date,
            amount_hours=waiver_in.amount_hours,
            reason_text=waiver_in.reason_text
        )

        adjustment = await self.repo.create(session, user_id=waiver_in.user_id, obj_in=adj_in)
        adjustment = await self.repo.update_status(
            session, adjustment, AdjustmentStatus.APPROVED, manager_id, "Abonado manualmente pelo gestor"
        )
        await audit_service.async_log_change(session, manager_id, "CREATE_WAIVER", new_model=adjustment)
        enriched = await self._enrich_adjustments_with_records(session, [adjustment])
        return enriched[0]

    @transactional
    async def admin_delete_adjustment(self, db: AsyncSession | None = None, adjustment_id: int = 0, admin_id: int = 0,
                                      reason: str = "") -> None:
        session = db if db is not None else self.db
        assert session is not None
        await self.repo.lock(session, adjustment_id)
        request = await self.repo.get(session, adjustment_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=adjustment_id)
        await self._validate_period_open(session, request.target_date)

        if request.adjustment_type not in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER, AdjustmentType.DAILY_EXCESS]:
            raise InvalidAdjustmentTypeError(adjustment_type=str(request.adjustment_type))

        if request.status == AdjustmentStatus.APPROVED:
            await self._revert_adjustment_action(session, request, admin_id)

        old_data = serialize_model(request)
        await self.repo.soft_delete(session, adjustment_id, admin_id)
        await audit_service.async_log_change(
            session, admin_id, "DELETE_ADJUSTMENT", old_model=old_data, new_data={"reason": reason}
        )

    @transactional
    async def delete_adjustment(self, db: AsyncSession | None = None, adjustment_id: int = 0, manager_id: int = 0,
                                reason: str = "") -> None:
        session = db if db is not None else self.db
        assert session is not None
        await self.repo.lock(session, adjustment_id)
        request = await self.repo.get(session, adjustment_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=adjustment_id)
        await self._validate_period_open(session, request.target_date)

        if request.adjustment_type not in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER, AdjustmentType.DAILY_EXCESS]:
            raise InvalidAdjustmentTypeError(adjustment_type=str(request.adjustment_type))

        if request.status == AdjustmentStatus.APPROVED:
            await self._revert_adjustment_action(session, request, manager_id)

        old_data = serialize_model(request)
        await self.repo.soft_delete(session, adjustment_id, manager_id)
        await audit_service.async_log_change(
            session, manager_id, "DELETE_ADJUSTMENT", old_model=old_data, new_data={"reason": reason}
        )

    async def upload_attachment(self, db: AsyncSession | None = None, request_id: int = 0,
                                file: UploadFile | None = None, user_id: int = 0):
        session = db if db is not None else self.db
        assert session is not None
        assert file is not None
        await self.repo.lock(session, request_id)
        request = await self.repo.get(session, request_id)
        if not request:
            raise AdjustmentNotFoundError("Solicitação de abono não encontrada.")

        if request.user_id != user_id:
            raise AdjustmentPermissionError("Acesso negado.")

        await self._validate_period_open(session, request.target_date)

        filename = (file.filename or "").lower()
        if "." not in filename:
            raise InvalidAdjustmentFilenameError("Nome de arquivo inválido.")

        file_ext = filename.split(".")[-1]
        allowed_extensions = {"pdf", "jpg", "jpeg", "png"}
        if file_ext not in allowed_extensions:
            raise InvalidAttachmentFormatError(
                "Formato inválido. Permitido apenas PDF, JPG ou PNG."
            )

        try:
            stored = await upload_storage.save(file, UploadCategory.ATTACHMENT)
        except DomainException as exc:
            if exc.status_code == 400:
                raise CorruptedAttachmentError(exc.detail) from exc
            raise
        try:
            async with unit_of_work(session):
                attachment = await self.repo.create_attachment(session, request_id, stored.relative_path, stored.content_type)
                await audit_service.async_log_change(
                    session, user_id, "UPLOAD_ATTACHMENT", entity="ADJUSTMENT", entity_id=request_id,
                    new_data={"file_name": stored.relative_path, "file_type": stored.content_type},
                )
            return attachment
        except BaseException:
            await session.rollback()
            await upload_storage.remove(stored)
            raise

    @transactional
    async def approve_adjustment(self, db: AsyncSession | None = None, request_id: int = 0, manager_id: int = 0,
                           comment: str | None = None, approved_amount_hours: float | None = None) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        await self.repo.lock(session, request_id)
        request = await self.repo.get(session, request_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=request_id)
        await self._validate_period_open(session, request.target_date)

        if request.status == AdjustmentStatus.APPROVED and request.adjustment_type != AdjustmentType.DAILY_EXCESS:
            return (await self._enrich_adjustments_with_records(session, [request]))[0]
        if request.adjustment_type == AdjustmentType.WAIVER:
            if not request.attachments:
                raise WaiverAttachmentRequiredError("Para aprovar um abono, é obrigatório haver anexo.")
        elif request.adjustment_type == AdjustmentType.DAILY_EXCESS:
            request.approved_amount_hours = approved_amount_hours
        elif request.adjustment_type != AdjustmentType.EXTRA_TIME:
            await self._execute_adjustment_action(session, request, manager_id)

        old_data = serialize_model(request)
        updated = await self.repo.update_status(session, request, AdjustmentStatus.APPROVED, manager_id, comment)
        await audit_service.async_log_change(
            session, manager_id, "APPROVE_ADJUSTMENT",
            old_model=old_data, new_model=updated,
            new_data={"comment": comment, "approved_amount_hours": approved_amount_hours} if (comment or approved_amount_hours is not None) else None
        )
        enriched = await self._enrich_adjustments_with_records(session, [updated])
        return enriched[0]

    async def _execute_adjustment_action(self, db: AsyncSession, request: AdjustmentRequest, manager_id: int):
        await adjustment_action(request.adjustment_type).apply(db, request, manager_id)

    @transactional
    async def reject_adjustment(self, db: AsyncSession | None = None, request_id: int = 0, manager_id: int = 0,
                          comment: str | None = None) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        await self.repo.lock(session, request_id)
        request = await self.repo.get(session, request_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=request_id)
        await self._validate_period_open(session, request.target_date)

        if request.status == AdjustmentStatus.APPROVED:
            await self._revert_adjustment_action(session, request, manager_id)

        old_data = serialize_model(request)
        updated = await self.repo.update_status(session, request, AdjustmentStatus.REJECTED, manager_id, comment)
        await audit_service.async_log_change(
            session, manager_id, "REJECT_ADJUSTMENT",
            old_model=old_data, new_model=updated,
            new_data={"comment": comment} if comment else None
        )
        enriched = await self._enrich_adjustments_with_records(session, [updated])
        return enriched[0]

    async def _revert_adjustment_action(self, db: AsyncSession, request: AdjustmentRequest, manager_id: int):
        await adjustment_action(request.adjustment_type).revert(db, request, manager_id)

    @transactional
    async def revert_adjustment_status(self, db: AsyncSession | None = None, request_id: int = 0, manager_id: int = 0,
                                       new_status: AdjustmentStatus | None = None,
                                 comment: str = "") -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        assert new_status is not None
        await self.repo.lock(session, request_id)
        request = await self.repo.get(session, request_id)
        if not request:
            raise AdjustmentNotFoundError(NOT_FOUND_MSG)

        await self._validate_period_open(session, request.target_date)

        old_status = request.status

        if old_status == new_status:
            enriched = await self._enrich_adjustments_with_records(session, [request])
            return enriched[0]

        if old_status == AdjustmentStatus.APPROVED and new_status in [AdjustmentStatus.PENDING,
                                                                      AdjustmentStatus.REJECTED]:
            await self._revert_adjustment_action(session, request, manager_id)

        elif (old_status in [AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED]
              and new_status == AdjustmentStatus.APPROVED
              and request.adjustment_type not in [AdjustmentType.WAIVER, AdjustmentType.EXTRA_TIME,
                                                  AdjustmentType.DAILY_EXCESS]):
            await self._execute_adjustment_action(session, request, manager_id)

        old_data = serialize_model(request)
        updated = await self.repo.update_status(session, request, new_status, manager_id, comment)
        await audit_service.async_log_change(
            session, manager_id, "REVERT_ADJUSTMENT",
            old_model=old_data, new_model=updated,
            new_data={"comment": comment} if comment else None
        )
        enriched = await self._enrich_adjustments_with_records(session, [updated])
        return enriched[0]

    async def get_attachment_file_path(
            self, db: AsyncSession | None = None, adjustment_id: int = 0, current_user: User | None = None
    ) -> tuple[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        adjustment = await self.repo.get(session, id=adjustment_id)
        if not adjustment:
            raise AdjustmentNotFoundError(adjustment_id=adjustment_id)

        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if adjustment.user_id != current_user.id and not is_manager:
            raise AdjustmentPermissionError("Acesso negado ao anexo.")

        if not adjustment.attachments:
            raise AdjustmentAttachmentNotFoundError("Nenhum anexo associado a este ajuste")

        attachment = adjustment.attachments[-1]
        safe_file_path = resolve_stored_file(attachment.file_path)
        if safe_file_path is None:
            raise AttachmentFileNotFoundError("Arquivo físico não encontrado no servidor")
        return str(safe_file_path), safe_file_path.name


adjustment_service = AdjustmentService()
