import os
import shutil
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.adjustments.adjustment_exceptions import (
    AdjustmentAttachmentNotFoundError,
    AdjustmentInvalidStatusError,
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
    BulkReprocessExtraTimeRequest,
)
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service, serialize_model
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_repository import get_local_time
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import AdjustmentStatus, AdjustmentType, UserRole
from app.shared.tolerance_cron_service import tolerance_cron_service

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

        min_dt = datetime.combine(min_date, datetime.min.time())
        max_dt = datetime.combine(max_date, datetime.max.time())

        stmt = select(TimeRecord).where(
            TimeRecord.user_id.in_(user_ids),
            TimeRecord.record_datetime >= min_dt,
            TimeRecord.record_datetime <= max_dt,
            TimeRecord.is_ignored.is_(False),
        ).order_by(TimeRecord.record_datetime.asc())
        result = await db.scalars(stmt)
        records = result.all()

        for adj in adjustments:
            adj.time_records = [
                r for r in records
                if r.user_id == adj.user_id and r.record_datetime.date() == adj.target_date
            ]

        return adjustments

    async def _validate_waiver_limit(self, db: AsyncSession, user_id: int, target_date: date,
                                     amount_hours: float | None):
        if not amount_hours:
            return

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

    async def create_adjustment_request(self, db: AsyncSession | None = None, user_id: int = 0,
                                  obj_in: AdjustmentRequestCreate | None = None) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        await self._validate_period_open(session, obj_in.target_date)

        if obj_in.adjustment_type == AdjustmentType.WAIVER:
            await self._validate_waiver_limit(session, user_id, obj_in.target_date, obj_in.amount_hours)

        adjustment = await self.repo.create(session, user_id=user_id, obj_in=obj_in)
        enriched = await self._enrich_adjustments_with_records(session, [adjustment])
        return enriched[0]

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

    async def admin_delete_adjustment(self, db: AsyncSession | None = None, adjustment_id: int = 0, admin_id: int = 0,
                                      reason: str = "") -> None:
        session = db if db is not None else self.db
        assert session is not None
        request = await self.repo.get(session, adjustment_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=adjustment_id)
        await self._validate_period_open(session, request.target_date)

        if request.adjustment_type not in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER]:
            raise InvalidAdjustmentTypeError(adjustment_type=str(request.adjustment_type))

        if request.status == AdjustmentStatus.APPROVED:
            await self._revert_adjustment_action(session, request, admin_id)

        old_data = serialize_model(request)
        await self.repo.soft_delete(session, adjustment_id, admin_id)
        await audit_service.async_log_change(
            session, admin_id, "DELETE_ADJUSTMENT", old_model=old_data, new_data={"reason": reason}
        )

    async def delete_adjustment(self, db: AsyncSession | None = None, adjustment_id: int = 0, manager_id: int = 0,
                                reason: str = "") -> None:
        session = db if db is not None else self.db
        assert session is not None
        request = await self.repo.get(session, adjustment_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=adjustment_id)
        await self._validate_period_open(session, request.target_date)

        if request.adjustment_type not in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER]:
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

        header = file.file.read(10)
        file.file.seek(0)
        is_valid = False

        if (
                (file_ext == "pdf" and header.startswith(b"%PDF")) or
                (file_ext == "png" and header.startswith(b"\x89PNG\r\n\x1a\n")) or
                (file_ext in ["jpg", "jpeg"] and header.startswith(b"\xff\xd8\xff"))
        ):
            is_valid = True

        if not is_valid:
            raise CorruptedAttachmentError(
                "O conteúdo do arquivo não corresponde à extensão ou está corrompido."
            )

        safe_filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        attachment = await self.repo.create_attachment(session, request_id, safe_filename, file.content_type or "")
        await audit_service.async_log_change(
            session, user_id, "UPLOAD_ATTACHMENT",
            entity="ADJUSTMENT", entity_id=request_id,
            new_data={"file_name": safe_filename, "file_type": file.content_type}
        )
        return attachment

    async def approve_adjustment(self, db: AsyncSession | None = None, request_id: int = 0, manager_id: int = 0,
                           comment: str | None = None) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        request = await self.repo.get(session, request_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=request_id)
        await self._validate_period_open(session, request.target_date)

        if request.adjustment_type == AdjustmentType.WAIVER:
            if not request.attachments:
                raise WaiverAttachmentRequiredError("Para aprovar um abono, é obrigatório haver anexo.")
        elif request.adjustment_type != AdjustmentType.EXTRA_TIME:
            await self._execute_adjustment_action(session, request, manager_id)

        old_data = serialize_model(request)
        updated = await self.repo.update_status(session, request, AdjustmentStatus.APPROVED, manager_id, comment)
        await audit_service.async_log_change(
            session, manager_id, "APPROVE_ADJUSTMENT",
            old_model=old_data, new_model=updated,
            new_data={"comment": comment} if comment else None
        )
        enriched = await self._enrich_adjustments_with_records(session, [updated])
        return enriched[0]

    async def _execute_adjustment_action(self, db: AsyncSession, request: AdjustmentRequest, manager_id: int):
        if not request.time:
            return
        target_dt = datetime.combine(request.target_date, request.time)
        if request.adjustment_type == AdjustmentType.DELETE_PUNCH:
            start_dt = target_dt.replace(second=0, microsecond=0)
            end_dt = target_dt.replace(second=59, microsecond=999999)

            stmt = select(TimeRecord).where(
                TimeRecord.user_id == request.user_id,
                TimeRecord.record_type == request.record_type,
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored.is_(False),
            )
            result = await db.scalars(stmt)
            record = result.first()
            if record:
                record.is_ignored = True
                record.deleted_at = get_local_time()
                record.deleted_by = manager_id
                await db.commit()
        else:
            time_rec = TimeRecord(
                user_id=request.user_id,
                record_type=request.record_type,
                record_datetime=target_dt,
                ip_address="ADJUSTMENT_APPROVED",
            )
            db.add(time_rec)
            await db.commit()
            await db.refresh(time_rec)

    async def cancel_adjustment(self, db: AsyncSession | None = None, request_id: int = 0,
                                user_id: int = 0) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        request = await self.repo.get(session, request_id)
        if not request:
            raise AdjustmentNotFoundError(adjustment_id=request_id)

        is_owner = request.user_id == user_id
        if not is_owner:
            raise AdjustmentPermissionError("Acesso negado. Apenas o proprietário do ajuste pode cancelá-lo.")

        if request.status != AdjustmentStatus.PENDING:
            raise AdjustmentInvalidStatusError(current_status=str(request.status))

        await self._validate_period_open(session, request.target_date)

        old_data = serialize_model(request)
        updated = await self.repo.update_status(session, request, AdjustmentStatus.CANCELED, user_id)
        await audit_service.async_log_change(
            session, user_id, "CANCEL_ADJUSTMENT",
            old_model=old_data, new_model=updated
        )
        enriched = await self._enrich_adjustments_with_records(session, [updated])
        return enriched[0]

    async def reject_adjustment(self, db: AsyncSession | None = None, request_id: int = 0, manager_id: int = 0,
                          comment: str | None = None) -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
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
        if request.adjustment_type in [AdjustmentType.EXTRA_TIME, AdjustmentType.WAIVER]:
            return

        if not request.time:
            return

        target_dt = datetime.combine(request.target_date, request.time)
        if request.adjustment_type == AdjustmentType.DELETE_PUNCH:
            start_dt = target_dt.replace(second=0, microsecond=0)
            end_dt = target_dt.replace(second=59, microsecond=999999)

            stmt = select(TimeRecord).where(
                TimeRecord.user_id == request.user_id,
                TimeRecord.record_type == request.record_type,
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored.is_(True),
            ).order_by(TimeRecord.deleted_at.desc())
            result = await db.scalars(stmt)
            record = result.first()
            if record:
                record.is_ignored = False
                record.deleted_at = None
                record.deleted_by = None
                await db.commit()
        elif request.adjustment_type in [AdjustmentType.FORGOT_PUNCH, AdjustmentType.PUNCH_NOT_COUNTED]:
            start_dt = target_dt.replace(second=0, microsecond=0)
            end_dt = target_dt.replace(second=59, microsecond=999999)

            stmt = select(TimeRecord).where(
                TimeRecord.user_id == request.user_id,
                TimeRecord.record_type == request.record_type,
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored.is_(False),
                TimeRecord.ip_address == "ADJUSTMENT_APPROVED",
            )
            result = await db.scalars(stmt)
            record = result.first()
            if record:
                record.is_ignored = True
                record.deleted_at = get_local_time()
                record.deleted_by = manager_id
                await db.commit()

    async def revert_adjustment_status(self, db: AsyncSession | None = None, request_id: int = 0, manager_id: int = 0,
                                       new_status: AdjustmentStatus | None = None,
                                 comment: str = "") -> AdjustmentRequest:
        session = db if db is not None else self.db
        assert session is not None
        assert new_status is not None
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

        elif old_status in [AdjustmentStatus.PENDING,
                            AdjustmentStatus.REJECTED] and new_status == AdjustmentStatus.APPROVED:
            if request.adjustment_type not in [AdjustmentType.WAIVER, AdjustmentType.EXTRA_TIME]:
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
        filename = os.path.basename(attachment.file_path)
        safe_file_path = os.path.join(settings.UPLOAD_DIR, filename)

        if not os.path.exists(safe_file_path):
            if os.path.exists(attachment.file_path):
                safe_file_path = attachment.file_path
            else:
                raise AttachmentFileNotFoundError(
                    "Arquivo físico não encontrado no servidor"
                )

        return safe_file_path, filename

    async def reprocess_historical_extra_time(
            self,
            db: AsyncSession | None = None,
            request_in: BulkReprocessExtraTimeRequest | None = None,
            current_user: User | None = None,
    ) -> dict[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        assert request_in is not None
        assert current_user is not None
        if current_user.role != UserRole.MAINTAINER:
            raise AdjustmentPermissionError(
                "Acesso negado. Requer privilégios de Mantenedor.",
            )

        curr = request_in.start_date.replace(day=1)
        while curr <= request_in.end_date:
            await self._validate_period_open(session, curr)
            if curr.month == 12:
                curr = curr.replace(year=curr.year + 1, month=1)
            else:
                curr = curr.replace(month=curr.month + 1)

        if hasattr(session, "sync_session"):
            await tolerance_cron_service.async_reprocess_historical_entries(
                db=session,
                start_date=request_in.start_date,
                end_date=request_in.end_date,
                user_ids=request_in.user_ids,
            )
        else:
            tolerance_cron_service.reprocess_historical_entries(
                db=session,
                start_date=request_in.start_date,
                end_date=request_in.end_date,
                user_ids=request_in.user_ids,
            )

        await audit_service.async_log_change(
            session,
            current_user.id,
            "REPROCESS",
            entity="EXTRA_TIME",
            entity_id=0,
            new_data={
                "start_date": str(request_in.start_date),
                "end_date": str(request_in.end_date),
                "user_ids": request_in.user_ids,
            },
        )

        return {"status": "success", "message": "Reprocessamento concluído com sucesso."}


adjustment_service = AdjustmentService()
