from datetime import datetime, time
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.security import get_client_device_name, get_client_ip
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service, serialize_model
from app.features.time_records.time_record_exceptions import TimeRecordNotFoundError
from app.features.time_records.time_record_models import TimeRecord, get_local_time
from app.features.time_records.time_record_repository import (
    AsyncTimeRecordRepository,
    async_time_record_repository,
    time_record_repository,
)
from app.features.time_records.time_record_schemas import (
    TimeRecordCreateAdmin,
    TimeRecordDeleteAdmin,
    TimeRecordUpdate,
)
from app.shared import deps
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType


class TimeRecordAdminService:
    def __init__(
        self,
        db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None,
        repo: Annotated[AsyncTimeRecordRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncTimeRecordRepository:
        return self._repo if self._repo is not None else async_time_record_repository


    async def _invalidate_extra_time_requests(self, db: Any, user_id: int, target_date: datetime.date):
        stmt = select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date == target_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
            AdjustmentRequest.status == AdjustmentStatus.PENDING,
        )
        if hasattr(db, "sync_session"):
            res = await db.scalars(stmt)
            requests = list(res.all())
            for req in requests:
                await db.delete(req)
            await db.flush()
        else:
            requests = db.query(AdjustmentRequest).filter(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date == target_date,
                AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
                AdjustmentRequest.status == AdjustmentStatus.PENDING,
            ).all()
            for req in requests:
                db.delete(req)
            db.flush()

    async def _is_first_entry_affected(self, db: Any, user_id: int, target_date: datetime.date,
                                 record_id: int | None = None, new_datetime: datetime | None = None) -> bool:
        start_of_day = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(settings.TIMEZONE))
        end_of_day = datetime.combine(target_date, time.max, tzinfo=ZoneInfo(settings.TIMEZONE))
        stmt = (
            select(TimeRecord)
            .where(
                TimeRecord.user_id == user_id,
                TimeRecord.record_type == RecordType.ENTRY,
                TimeRecord.deleted_at.is_(None),
                TimeRecord.record_datetime >= start_of_day,
                TimeRecord.record_datetime <= end_of_day,
            )
            .order_by(TimeRecord.record_datetime.asc())
        )
        if hasattr(db, "sync_session"):
            first_entry = (await db.scalars(stmt)).first()
        else:
            first_entry = (db.query(TimeRecord).filter(
                TimeRecord.user_id == user_id,
                TimeRecord.record_type == RecordType.ENTRY,
                TimeRecord.deleted_at.is_(None),
                TimeRecord.record_datetime >= start_of_day,
                TimeRecord.record_datetime <= end_of_day,
            ).order_by(TimeRecord.record_datetime.asc()).first())

        if not first_entry:
            return new_datetime is not None
        if record_id is not None and first_entry.id == record_id:
            return True
        if new_datetime is not None:
            if new_datetime <= first_entry.record_datetime:
                return True
        return False

    async def _validate_period_open_helper(self, session: Any, date: datetime.date):
        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, date)
        else:
            payroll_service.validate_period_open(session, date)

    async def _commit_and_audit_admin_create(self, session: Any, manager_id: int, record: TimeRecord):
        if hasattr(session, "sync_session"):
            await session.flush()
            await session.commit()
            await session.refresh(record)
            await audit_service.async_log_change(session, manager_id, "CREATE_RECORD_ADMIN", new_model=record)
        else:
            session.flush()
            session.commit()
            session.refresh(record)
            audit_service.log_change(session, manager_id, "CREATE_RECORD_ADMIN", new_model=record)

    def _resolve_admin_metadata(
            self,
            request: Request | None,
            ip_address: str | None,
            device_name: str | None,
            platform: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        if request is None:
            return ip_address, device_name, platform
        resolved_ip = ip_address or get_client_ip(request)
        resolved_device = device_name or get_client_device_name(resolved_ip, request)
        header_plat = request.headers.get("X-Platform", "").lower()
        resolved_platform = header_plat if header_plat else platform
        return resolved_ip, resolved_device, resolved_platform

    async def _get_record_by_id(self, session: Any, record_id: int) -> TimeRecord:
        if hasattr(session, "sync_session"):
            record = await self.repo.get(session, record_id)
        else:
            record = time_record_repository.get(session, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)
        return record

    async def _handle_admin_update_invalidations(self, db: Any, record: TimeRecord, obj_in: TimeRecordUpdate,
                                           old_date: datetime.date, new_date: datetime.date,
                                           new_record_type: RecordType):
        if record.record_type == RecordType.ENTRY:
            if await self._is_first_entry_affected(db, record.user_id, old_date, record_id=record.id):
                await self._invalidate_extra_time_requests(db, record.user_id, old_date)
        if new_record_type == RecordType.ENTRY:
            new_dt = obj_in.record_datetime if obj_in.record_datetime else record.record_datetime
            if await self._is_first_entry_affected(db, record.user_id, new_date, record_id=record.id,
                                                   new_datetime=new_dt):
                await self._invalidate_extra_time_requests(db, record.user_id, new_date)

    def _build_updated_admin_record(
            self,
            record: TimeRecord,
            obj_in: TimeRecordUpdate,
            manager_id: int,
            ip_address: str | None,
            device_name: str | None,
            platform: str | None,
            new_record_type: RecordType,
            new_record_datetime: datetime,
    ) -> TimeRecord:
        return TimeRecord(
            user_id=record.user_id,
            record_type=new_record_type,
            record_datetime=new_record_datetime,
            ip_address=ip_address,
            device_name=device_name if device_name else "",
            platform=platform,
            biometric_id=None,
            edited_by=manager_id,
            edit_justification=obj_in.edit_justification,
            original_record_id=record.original_record_id if record.original_record_id else record.id,
            created_at=get_local_time(),
            is_verified=True,
        )

    async def _commit_and_audit_admin_update(self, session: Any, manager_id: int, old_data: dict,
                                             new_record: TimeRecord):
        if hasattr(session, "sync_session"):
            await session.flush()
            await session.commit()
            await session.refresh(new_record)
            await audit_service.async_log_change(session, manager_id, "UPDATE_RECORD_ADMIN", old_model=old_data,
                                                 new_model=new_record)
        else:
            session.flush()
            session.commit()
            session.refresh(new_record)
            audit_service.log_change(session, manager_id, "UPDATE_RECORD_ADMIN", old_model=old_data,
                                     new_model=new_record)

    async def _commit_and_audit_admin_delete(self, session: Any, manager_id: int, old_data: dict,
                                             justification: str):
        if hasattr(session, "sync_session"):
            await self.repo.delete(session, old_data.get("id"), manager_id)
            await session.flush()
            await session.commit()
            await audit_service.async_log_change(session, manager_id, "DELETE_RECORD_ADMIN", old_model=old_data,
                                                 new_data={"justification": justification})
        else:
            time_record_repository.delete(session, old_data.get("id"), manager_id)
            session.flush()
            session.commit()
            audit_service.log_change(session, manager_id, "DELETE_RECORD_ADMIN", old_model=old_data,
                                     new_data={"justification": justification})

    def _extract_delete_justification(
            self,
            justification: str | None,
            request_body: TimeRecordDeleteAdmin | None,
            obj_in: TimeRecordDeleteAdmin | None,
    ) -> str | None:
        if justification and justification.strip():
            return justification.strip()
        if request_body and request_body.edit_justification and request_body.edit_justification.strip():
            return request_body.edit_justification.strip()
        if obj_in and obj_in.edit_justification and obj_in.edit_justification.strip():
            return obj_in.edit_justification.strip()
        return None

    def _resolve_delete_obj_in(
            self,
            validate_justification: bool,
            justification: str | None,
            request_body: TimeRecordDeleteAdmin | None,
            obj_in: TimeRecordDeleteAdmin | None,
    ) -> TimeRecordDeleteAdmin:
        if not validate_justification:
            assert obj_in is not None
            return obj_in

        justification_val = self._extract_delete_justification(justification, request_body, obj_in)
        if not justification_val:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Justificativa de exclusão é obrigatória.",
            )
        return TimeRecordDeleteAdmin(edit_justification=justification_val)

    async def _handle_delete_invalidations(self, session: Any, record: TimeRecord) -> None:
        if record.record_type == RecordType.ENTRY:
            if await self._is_first_entry_affected(session, record.user_id, record.record_datetime.date(),
                                                   record_id=record.id):
                await self._invalidate_extra_time_requests(session, record.user_id, record.record_datetime.date())

    async def create_admin_record(self, db: Any | None = None, obj_in: TimeRecordCreateAdmin | None = None,
                                  manager_id: int = 0, ip_address: str = "",
                                  device_name: str | None = None, platform: str = "WEB_ADMIN",
                                  request: Request | None = None) -> TimeRecord:
        resolved_ip, device_name, resolved_platform = self._resolve_admin_metadata(request, ip_address, device_name,
                                                                                   platform)
        ip_address = resolved_ip if resolved_ip else ""
        platform = resolved_platform if resolved_platform else platform
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        await self._validate_period_open_helper(session, obj_in.record_datetime.date())

        if obj_in.record_type == RecordType.ENTRY:
            if await self._is_first_entry_affected(session, obj_in.user_id, obj_in.record_datetime.date(),
                                             new_datetime=obj_in.record_datetime):
                await self._invalidate_extra_time_requests(session, obj_in.user_id, obj_in.record_datetime.date())


        if hasattr(session, "sync_session"):
            record = await self.repo.create(session, user_id=obj_in.user_id, record_type=obj_in.record_type,
                                            record_datetime=obj_in.record_datetime, ip_address=ip_address,
                                            device_name=device_name if device_name else "", platform=platform)
        else:
            record = time_record_repository.create(session, user_id=obj_in.user_id, record_type=obj_in.record_type,
                                                   record_datetime=obj_in.record_datetime, ip_address=ip_address,
                                                   device_name=device_name if device_name else "", platform=platform)
        record.edited_by = manager_id
        record.edit_justification = obj_in.edit_justification
        record.is_verified = True
        session.add(record)
        await self._commit_and_audit_admin_create(session, manager_id, record)
        return record

    async def update_admin_record(self, db: Any | None = None, record_id: int = 0,
                                  obj_in: TimeRecordUpdate | None = None, manager_id: int = 0,
                                  ip_address: str | None = None, device_name: str | None = None,
                                  platform: str | None = None,
                                  request: Request | None = None) -> TimeRecord:
        ip_address, device_name, platform = self._resolve_admin_metadata(request, ip_address, device_name, platform)
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        record = await self._get_record_by_id(session, record_id)

        await self._validate_period_open_helper(session, record.record_datetime.date())
        if obj_in.record_datetime:
            await self._validate_period_open_helper(session, obj_in.record_datetime.date())

        new_record_type = obj_in.record_type if obj_in.record_type else record.record_type
        new_record_datetime = obj_in.record_datetime if obj_in.record_datetime else record.record_datetime
        if new_record_type == record.record_type and new_record_datetime == record.record_datetime:
            return record
        old_date = record.record_datetime.date()
        new_date = obj_in.record_datetime.date() if obj_in.record_datetime else old_date
        await self._handle_admin_update_invalidations(session, record, obj_in, old_date, new_date, new_record_type)

        old_data = serialize_model(record)
        record.is_ignored = True
        new_record = self._build_updated_admin_record(
            record, obj_in, manager_id, ip_address, device_name, platform, new_record_type, new_record_datetime
        )
        session.add(new_record)
        session.add(record)
        await self._commit_and_audit_admin_update(session, manager_id, old_data, new_record)
        return new_record

    async def delete_admin_record(self, db: Any | None = None, record_id: int = 0,
                                  obj_in: TimeRecordDeleteAdmin | None = None, manager_id: int = 0,
                                  justification: str | None = None,
                                  request_body: TimeRecordDeleteAdmin | None = None,
                                  validate_justification: bool = False):
        session = db if db is not None else self.db
        assert session is not None

        resolved_obj_in = self._resolve_delete_obj_in(validate_justification, justification, request_body, obj_in)
        record = await self._get_record_by_id(session, record_id)

        await self._validate_period_open_helper(session, record.record_datetime.date())
        await self._handle_delete_invalidations(session, record)

        justification_val = resolved_obj_in.edit_justification if resolved_obj_in.edit_justification else ""
        old_data = serialize_model(record)
        await self._commit_and_audit_admin_delete(session, manager_id, old_data, justification_val)
