from datetime import datetime, time
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_client_device_name, get_client_ip
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.companies.company_repository import (
    async_company_repository,
    company_repository,
)
from app.features.payroll.payroll_service import payroll_service
from app.features.printers.printer_repository import (
    async_printer_repository,
    printer_repository,
)
from app.features.system.audit_service import audit_service, serialize_model
from app.features.time_records.receipt_service import receipt_service
from app.features.time_records.time_record_exceptions import (
    InvalidReceiptIdError,
    ManualPunchUnauthorizedError,
    ReceiptAccessDeniedError,
    TimeRecordAccessDeniedError,
    TimeRecordNotFoundError,
    TimeRecordUserNotFoundError,
)
from app.features.time_records.time_record_models import (
    TimeRecord,
    get_local_time,
)
from app.features.time_records.time_record_repository import (
    AsyncTimeRecordRepository,
    async_time_record_repository,
    time_record_repository,
)
from app.features.time_records.time_record_schemas import (
    ReceiptResponse,
    ReceiptTimelineItem,
    TimeRecordCreateAdmin,
    TimeRecordDeleteAdmin,
    TimeRecordUpdate,
)
from app.features.users.user_models import User
from app.features.users.user_repository import (
    async_user_repository,
    user_repository,
)
from app.shared import deps
from app.shared.enums import (
    AdjustmentStatus,
    AdjustmentType,
    RecordType,
    UserRole,
)
from app.shared.daily_excess_cron_service import daily_excess_cron_service
from app.shared.hashid_service import hashid_service
from app.shared.trusted_time_service import trusted_time_service
from app.utils.formatters import mask_cnpj, mask_cpf


class TimeRecordService:
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

    async def _invalidate_daily_excess_and_unverify(self, db: Any, user_id: int, target_date: datetime.date):
        stmt = select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date == target_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        )
        if hasattr(db, "sync_session"):
            res = await db.scalars(stmt)
            requests = list(res.all())
            for req in requests:
                await db.delete(req)
        else:
            requests = db.query(AdjustmentRequest).filter(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date == target_date,
                AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
                AdjustmentRequest.deleted_at.is_(None),
            ).all()
            for req in requests:
                db.delete(req)

        tz = ZoneInfo(settings.TIMEZONE)
        start_of_day = datetime.combine(target_date, time.min, tzinfo=tz)
        end_of_day = datetime.combine(target_date, time.max, tzinfo=tz)
        if hasattr(db, "sync_session"):
            rec_stmt = select(TimeRecord).where(
                TimeRecord.user_id == user_id,
                TimeRecord.record_datetime >= start_of_day,
                TimeRecord.record_datetime <= end_of_day,
                TimeRecord.deleted_at.is_(None),
            )
            recs = list((await db.scalars(rec_stmt)).all())
            for r in recs:
                r.is_verified = False
            await db.flush()
        else:
            recs = db.query(TimeRecord).filter(
                TimeRecord.user_id == user_id,
                TimeRecord.record_datetime >= start_of_day,
                TimeRecord.record_datetime <= end_of_day,
                TimeRecord.deleted_at.is_(None),
            ).all()
            for r in recs:
                r.is_verified = False
            db.flush()

    async def _reprocess_daily_excess(self, db: Any, user_id: int, target_date: datetime.date):
        if hasattr(db, "sync_session"):
            await daily_excess_cron_service.evaluate_user_day_async(db, user_id, target_date)
        else:
            daily_excess_cron_service.evaluate_user_day_sync(db, user_id, target_date)

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

    async def _validate_manual_punch_permission(self, db: Any, user_id: int, request: Request):
        if hasattr(db, "sync_session"):
            user = await async_user_repository.get(db, user_id)
        else:
            user = user_repository.get(db, user_id)
        if not user:
            raise TimeRecordUserNotFoundError()
        if user.role in [UserRole.MANAGER, UserRole.MAINTAINER]:
            return
        platform = request.headers.get("X-Platform", "desktop").lower()
        can_punch = False
        if platform == "mobile":
            can_punch = user.can_manual_punch_mobile
        else:
            can_punch = user.can_manual_punch_desktop
        if can_punch:
            return
        raise ManualPunchUnauthorizedError()

    async def register_entry(self, db: Any | None = None, user_id: int = 0,
                             request: Request | None = None) -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert request is not None
        await self._validate_manual_punch_permission(session, user_id, request)
        current_time, used_ntp = trusted_time_service.get_trusted_time()
        ip_address = get_client_ip(request)
        device_name = get_client_device_name(ip_address, request)
        platform = request.headers.get("X-Platform", "desktop").lower()
        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, current_time.date())
        else:
            payroll_service.validate_period_open(session, current_time.date())

        if hasattr(session, "sync_session"):
            record = await self.repo.create(
                session,
                user_id=user_id,
                record_type=RecordType.ENTRY,
                record_datetime=current_time,
                ip_address=ip_address,
                device_name=device_name,
                platform=platform,
            )
        else:
            record = time_record_repository.create(
                session,
                user_id=user_id,
                record_type=RecordType.ENTRY,
                record_datetime=current_time,
                ip_address=ip_address,
                device_name=device_name,
                platform=platform,
            )

        if not used_ntp:
            request.state.ntp_error = True
            record.edit_justification = "Registro feito com a hora local do servidor (Falha no NTP)."
            session.add(record)
            if hasattr(session, "sync_session"):
                await session.commit()
                await session.refresh(record)
                await audit_service.async_log_change(session, user_id, "NTP_FALLBACK", entity="TIME_RECORD",
                                                     entity_id=record.id,
                                                     new_data={"justification": record.edit_justification})
            else:
                session.commit()
                session.refresh(record)
                audit_service.log_change(session, user_id, "NTP_FALLBACK", entity="TIME_RECORD", entity_id=record.id,
                                         new_data={"justification": record.edit_justification})
        return record

    async def register_exit(self, db: Any | None = None, user_id: int = 0,
                            request: Request | None = None) -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert request is not None
        await self._validate_manual_punch_permission(session, user_id, request)
        current_time, used_ntp = trusted_time_service.get_trusted_time()
        ip_address = get_client_ip(request)
        device_name = get_client_device_name(ip_address, request)
        platform = request.headers.get("X-Platform", "desktop").lower()
        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, current_time.date())
        else:
            payroll_service.validate_period_open(session, current_time.date())

        if hasattr(session, "sync_session"):
            record = await self.repo.create(
                session,
                user_id=user_id,
                record_type=RecordType.EXIT,
                record_datetime=current_time,
                ip_address=ip_address,
                device_name=device_name,
                platform=platform,
            )
        else:
            record = time_record_repository.create(
                session,
                user_id=user_id,
                record_type=RecordType.EXIT,
                record_datetime=current_time,
                ip_address=ip_address,
                device_name=device_name,
                platform=platform,
            )

        if not used_ntp:
            request.state.ntp_error = True
            record.edit_justification = "Registro feito com a hora local do servidor (Falha no NTP)."
            session.add(record)
            if hasattr(session, "sync_session"):
                await session.commit()
                await session.refresh(record)
                await audit_service.async_log_change(session, user_id, "NTP_FALLBACK", entity="TIME_RECORD",
                                                     entity_id=record.id,
                                                     new_data={"justification": record.edit_justification})
            else:
                session.commit()
                session.refresh(record)
                audit_service.log_change(session, user_id, "NTP_FALLBACK", entity="TIME_RECORD", entity_id=record.id,
                                         new_data={"justification": record.edit_justification})
        return record

    async def _process_toggle_invalidations(self, db: Any, record: TimeRecord, new_type: RecordType):
        previous_type = record.record_type
        target_date = record.record_datetime.date()

        if previous_type == RecordType.ENTRY:
            if await self._is_first_entry_affected(db, record.user_id, target_date, record_id=record.id):
                await self._invalidate_extra_time_requests(db, record.user_id, target_date)

        if new_type == RecordType.ENTRY:
            if await self._is_first_entry_affected(db, record.user_id, target_date,
                                                   new_datetime=record.record_datetime):
                await self._invalidate_extra_time_requests(db, record.user_id, target_date)

        await self._invalidate_daily_excess_and_unverify(db, record.user_id, target_date)

    def _create_toggled_record(self, record: TimeRecord, new_type: RecordType, current_user: User,
                               is_manager: bool) -> TimeRecord:
        original_id = record.original_record_id if record.original_record_id else record.id
        return TimeRecord(
            user_id=record.user_id,
            record_type=new_type,
            record_datetime=record.record_datetime,
            ip_address=record.ip_address,
            device_name=record.device_name,
            platform=record.platform,
            biometric_id=record.biometric_id,
            edited_by=current_user.id,
            edit_justification="Inversão de marcação efetuada",
            original_record_id=original_id,
            created_at=record.created_at,
            is_verified=bool(is_manager)
        )

    async def toggle_record_type(self, db: Any | None = None, record_id: int = 0,
                                 current_user: User | None = None) -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        if hasattr(session, "sync_session"):
            record = await self.repo.get(session, record_id)
        else:
            record = time_record_repository.get(session, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)

        is_owner = record.user_id == current_user.id
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if not is_owner and not is_manager:
            raise TimeRecordAccessDeniedError()

        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, record.record_datetime.date())
        else:
            payroll_service.validate_period_open(session, record.record_datetime.date())

        new_type = RecordType.EXIT if record.record_type == RecordType.ENTRY else RecordType.ENTRY
        await self._process_toggle_invalidations(session, record, new_type)

        old_data = serialize_model(record)
        record.is_ignored = True
        new_record = self._create_toggled_record(record, new_type, current_user, is_manager)

        session.add(new_record)
        if hasattr(session, "sync_session"):
            await session.flush()
            session.add(record)
            await self._reprocess_daily_excess(session, record.user_id, record.record_datetime.date())
            await session.commit()
            await session.refresh(new_record)
            await audit_service.async_log_change(session, current_user.id, "TOGGLE_RECORD", old_model=old_data,
                                                 new_model=new_record)
        else:
            session.flush()
            session.add(record)
            await self._reprocess_daily_excess(session, record.user_id, record.record_datetime.date())
            session.commit()
            session.refresh(new_record)
            audit_service.log_change(session, current_user.id, "TOGGLE_RECORD", old_model=old_data,
                                     new_model=new_record)
        return new_record

    async def create_admin_record(self, db: Any | None = None, obj_in: TimeRecordCreateAdmin | None = None,
                                  manager_id: int = 0, ip_address: str = "",
                            device_name: str | None = None, platform: str = "WEB_ADMIN") -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, obj_in.record_datetime.date())
        else:
            payroll_service.validate_period_open(session, obj_in.record_datetime.date())

        if obj_in.record_type == RecordType.ENTRY:
            if await self._is_first_entry_affected(session, obj_in.user_id, obj_in.record_datetime.date(),
                                             new_datetime=obj_in.record_datetime):
                await self._invalidate_extra_time_requests(session, obj_in.user_id, obj_in.record_datetime.date())

        await self._invalidate_daily_excess_and_unverify(session, obj_in.user_id, obj_in.record_datetime.date())

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
        if hasattr(session, "sync_session"):
            await session.flush()
            await self._reprocess_daily_excess(session, obj_in.user_id, obj_in.record_datetime.date())
            await session.commit()
            await session.refresh(record)
            await audit_service.async_log_change(session, manager_id, "CREATE_RECORD_ADMIN", new_model=record)
        else:
            session.flush()
            await self._reprocess_daily_excess(session, obj_in.user_id, obj_in.record_datetime.date())
            session.commit()
            session.refresh(record)
            audit_service.log_change(session, manager_id, "CREATE_RECORD_ADMIN", new_model=record)
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

        await self._invalidate_daily_excess_and_unverify(db, record.user_id, old_date)
        if new_date != old_date:
            await self._invalidate_daily_excess_and_unverify(db, record.user_id, new_date)

    async def update_admin_record(self, db: Any | None = None, record_id: int = 0,
                                  obj_in: TimeRecordUpdate | None = None, manager_id: int = 0,
                             ip_address: str | None = None, device_name: str | None = None,
                             platform: str | None = None) -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        if hasattr(session, "sync_session"):
            record = await self.repo.get(session, record_id)
        else:
            record = time_record_repository.get(session, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)

        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, record.record_datetime.date())
            if obj_in.record_datetime:
                await payroll_service.async_validate_period_open(session, obj_in.record_datetime.date())
        else:
            payroll_service.validate_period_open(session, record.record_datetime.date())
            if obj_in.record_datetime:
                payroll_service.validate_period_open(session, obj_in.record_datetime.date())

        new_record_type = obj_in.record_type if obj_in.record_type else record.record_type
        new_record_datetime = obj_in.record_datetime if obj_in.record_datetime else record.record_datetime
        if new_record_type == record.record_type and new_record_datetime == record.record_datetime:
            return record
        old_date = record.record_datetime.date()
        new_date = obj_in.record_datetime.date() if obj_in.record_datetime else old_date
        await self._handle_admin_update_invalidations(session, record, obj_in, old_date, new_date, new_record_type)

        old_data = serialize_model(record)
        record.is_ignored = True
        new_record = TimeRecord(user_id=record.user_id, record_type=new_record_type,
                                record_datetime=new_record_datetime, ip_address=ip_address,
                                device_name=device_name if device_name else "", platform=platform, biometric_id=None,
                                edited_by=manager_id, edit_justification=obj_in.edit_justification,
                                original_record_id=record.original_record_id if record.original_record_id else record.id,
                                created_at=get_local_time(), is_verified=True)
        session.add(new_record)
        session.add(record)
        if hasattr(session, "sync_session"):
            await session.flush()
            await self._reprocess_daily_excess(session, record.user_id, old_date)
            if new_date != old_date:
                await self._reprocess_daily_excess(session, record.user_id, new_date)
            await session.commit()
            await session.refresh(new_record)
            await audit_service.async_log_change(session, manager_id, "UPDATE_RECORD_ADMIN", old_model=old_data,
                                                 new_model=new_record)
        else:
            session.flush()
            await self._reprocess_daily_excess(session, record.user_id, old_date)
            if new_date != old_date:
                await self._reprocess_daily_excess(session, record.user_id, new_date)
            session.commit()
            session.refresh(new_record)
            audit_service.log_change(session, manager_id, "UPDATE_RECORD_ADMIN", old_model=old_data,
                                     new_model=new_record)
        return new_record

    async def delete_admin_record(self, db: Any | None = None, record_id: int = 0,
                                  obj_in: TimeRecordDeleteAdmin | None = None, manager_id: int = 0):
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        if hasattr(session, "sync_session"):
            record = await self.repo.get(session, record_id)
        else:
            record = time_record_repository.get(session, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)

        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, record.record_datetime.date())
        else:
            payroll_service.validate_period_open(session, record.record_datetime.date())

        if record.record_type == RecordType.ENTRY:
            if await self._is_first_entry_affected(session, record.user_id, record.record_datetime.date(),
                                                   record_id=record.id):
                await self._invalidate_extra_time_requests(session, record.user_id, record.record_datetime.date())

        target_date = record.record_datetime.date()
        user_id = record.user_id
        justification_val = obj_in.edit_justification if obj_in.edit_justification else ""
        old_data = serialize_model(record)
        if hasattr(session, "sync_session"):
            await self.repo.delete(session, record_id, manager_id)
            await session.flush()
            await self._reprocess_daily_excess(session, user_id, target_date)
            await session.commit()
            await audit_service.async_log_change(session, manager_id, "DELETE_RECORD_ADMIN", old_model=old_data,
                                                 new_data={"justification": justification_val})
        else:
            time_record_repository.delete(session, record_id, manager_id)
            session.flush()
            await self._reprocess_daily_excess(session, user_id, target_date)
            session.commit()
            audit_service.log_change(session, manager_id, "DELETE_RECORD_ADMIN", old_model=old_data,
                                     new_data={"justification": justification_val})

    async def _determine_punch_type(self, db: Any, user_id: int, timestamp: datetime) -> RecordType:
        if hasattr(db, "sync_session"):
            last_record = await self.repo.get_last_by_user(db, user_id)
        else:
            last_record = time_record_repository.get_last_by_user(db, user_id)
        if not last_record or last_record.record_type != RecordType.ENTRY:
            return RecordType.ENTRY

        tz = ZoneInfo(settings.TIMEZONE)
        last_time = last_record.record_datetime
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=ZoneInfo("UTC"))
        last_local_date = last_time.astimezone(tz).date()

        curr_time = timestamp
        if curr_time.tzinfo is None:
            curr_time = curr_time.replace(tzinfo=ZoneInfo("UTC"))
        curr_local_date = curr_time.astimezone(tz).date()

        if last_local_date == curr_local_date:
            return RecordType.EXIT
        return RecordType.ENTRY

    async def create_punch(self, db: Any | None = None, user_id: int = 0, timestamp: datetime | None = None,
                           ip_address: str = "",
                     biometric_id: int | None = None, platform: str = "desktop") -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert timestamp is not None
        record_type = await self._determine_punch_type(session, user_id, timestamp)
        device_name = get_client_device_name(ip_address)
        if hasattr(session, "sync_session"):
            return await self.repo.create(
                session,
                user_id=user_id,
                record_type=record_type,
                record_datetime=timestamp,
                ip_address=ip_address,
                device_name=device_name,
                platform=platform,
                biometric_id=biometric_id,
            )
        return time_record_repository.create(
            session,
            user_id=user_id,
            record_type=record_type,
            record_datetime=timestamp,
            ip_address=ip_address,
            device_name=device_name,
            platform=platform,
            biometric_id=biometric_id,
        )

    async def get_my_records(self, db: Any | None = None, user_id: int = 0, skip: int = 0, limit: int = 100) -> list[
        TimeRecord]:
        session = db if db is not None else self.db
        assert session is not None
        if hasattr(session, "sync_session"):
            return await self.repo.get_all_by_user(session, user_id, skip, limit)
        return time_record_repository.get_all_by_user(session, user_id, skip, limit)

    async def list_records_for_admin(self, db: Any | None = None, user_id: int = 0, start_date: datetime | None = None,
                                     end_date: datetime | None = None) -> list[
        TimeRecord]:
        session = db if db is not None else self.db
        assert session is not None
        assert start_date is not None
        assert end_date is not None
        if hasattr(session, "sync_session"):
            return await self.repo.get_by_range(session, user_id, start_date, end_date)
        return time_record_repository.get_by_range(session, user_id, start_date, end_date)

    async def get_record_timeline(self, db: Any | None = None, record_id: int = 0) -> list[TimeRecord]:
        session = db if db is not None else self.db
        assert session is not None
        if hasattr(session, "sync_session"):
            return await self.repo.get_timeline(session, record_id)
        return time_record_repository.get_timeline(session, record_id)

    def _build_print_data(self, record: TimeRecord, company, short_id: str) -> dict:
        record_type_str = "Entrada" if record.record_type == RecordType.ENTRY else "Saída"
        company_cnpj = mask_cnpj(company.cnpj or "") if company.cnpj else "N/A"
        employee_cpf = mask_cpf(record.user.cpf or "")

        return {
            "company_name": company.name,
            "company_address": company.address or "N/A",
            "company_cnpj": company_cnpj,
            "employee_name": record.user.name,
            "employee_cpf": employee_cpf,
            "employee_pis": record.user.pis or "N/A",
            "record_date": record.record_datetime.strftime("%d/%m/%Y"),
            "record_time": record.record_datetime.strftime("%H:%M"),
            "record_type_str": record_type_str,
            "device_name": record.device_name or "Desconhecido",
            "nsr": record.id,
            "short_id": short_id.upper(),
        }

    async def trigger_auto_print(self, db: Any | None = None, record: TimeRecord | None = None, background_tasks=None):
        session = db if db is not None else self.db
        assert session is not None
        assert record is not None
        if hasattr(session, "sync_session"):
            company = await async_company_repository.get_current(session)
        else:
            company = company_repository.get_current(session)
        if not company or not company.default_printer_id:
            return

        should_print = record.user.auto_print_receipt
        if should_print is None:
            should_print = company.auto_print_receipt

        if not should_print:
            return

        if hasattr(session, "sync_session"):
            printer = await async_printer_repository.get_by_id(session, company.default_printer_id)
        else:
            printer = printer_repository.get_by_id(session, company.default_printer_id)
        if not printer or not printer.status:
            return

        short_id = hashid_service.encode(record.id)
        data = self._build_print_data(record, company, short_id)
        background_tasks.add_task(receipt_service.print_receipt_async, printer, data)

    async def _get_accessible_record(self, db: Any, short_id: str, current_user: User) -> TimeRecord:
        record_id = hashid_service.decode(short_id)
        if not record_id:
            raise InvalidReceiptIdError(receipt_id=short_id)

        if hasattr(db, "sync_session"):
            record = await self.repo.get(db, record_id)
        else:
            record = time_record_repository.get(db, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)

        if current_user.role == UserRole.EMPLOYEE and record.user_id != current_user.id:
            raise ReceiptAccessDeniedError()
        return record

    def _build_receipt_timeline(self, timeline: list[TimeRecord]) -> list[ReceiptTimelineItem]:
        timeline_items: list[ReceiptTimelineItem] = []
        if timeline and hasattr(timeline[0], "action"):
            for t in timeline:
                timeline_items.append(
                    ReceiptTimelineItem(
                        action=t.action,
                        timestamp=t.timestamp,
                        user_name=t.user.name if t.user else None,
                        old_data=t.old_data,
                        new_data=t.new_data,
                    )
                )
        return timeline_items

    async def get_receipt_data(self, db: Any | None = None, short_id: str = "", current_user: User | None = None):
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        record = await self._get_accessible_record(session, short_id, current_user)
        if hasattr(session, "sync_session"):
            company = await async_company_repository.get_current(session)
            timeline = await self.get_record_timeline(session, record.id)
        else:
            company = company_repository.get_current(session)
            timeline = await self.get_record_timeline(session, record.id)
        timeline_items = self._build_receipt_timeline(timeline)

        return ReceiptResponse(
            short_id=short_id,
            record_id=record.id,
            company_name=company.name if company else "N/A",
            company_cnpj=mask_cnpj(company.cnpj or "") if (company and company.cnpj) else "N/A",
            company_address=company.address if company else "N/A",
            employee_name=record.user.name,
            employee_cpf=mask_cpf(record.user.cpf or ""),
            employee_pis=record.user.pis,
            record_datetime=record.record_datetime,
            device_name=record.device_name or "Desconhecido",
            record_type=record.record_type,
            timeline=timeline_items,
        )

    async def get_receipt_pdf(self, db: Any | None = None, short_id: str = "", current_user: User | None = None) -> \
            tuple[bytes, str]:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        record = await self._get_accessible_record(session, short_id, current_user)
        if hasattr(session, "sync_session"):
            company = await async_company_repository.get_current(session)
        else:
            company = company_repository.get_current(session)

        record_type_str = "Entrada" if record.record_type == RecordType.ENTRY else "Saída"
        date_str = record.record_datetime.strftime("%d/%m/%Y")
        time_str = record.record_datetime.strftime("%H:%M")

        data = {
            "company_name": company.name if company else "N/A",
            "company_address": company.address if company else "N/A",
            "company_cnpj": mask_cnpj(company.cnpj or "") if company else "N/A",
            "employee_name": record.user.name,
            "employee_cpf": mask_cpf(record.user.cpf or ""),
            "employee_pis": record.user.pis,
            "record_date": date_str,
            "record_time": time_str,
            "record_type_str": record_type_str,
            "device_name": record.device_name or "Desconhecido",
            "nsr": record.id,
            "short_id": short_id.upper(),
        }

        pdf_bytes = receipt_service.generate_pdf_receipt(data)
        filename = f"{record.id}.pdf"
        return pdf_bytes, filename


time_record_service = TimeRecordService()
