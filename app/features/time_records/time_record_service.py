from datetime import datetime
from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.security import get_client_device_name, get_client_ip
from app.features.companies.company_repository import (
    async_company_repository,
    company_repository,
)
from app.features.printers.printer_repository import (
    async_printer_repository,
    printer_repository,
)
from app.features.system.audit_service import audit_service, serialize_model
from app.features.time_records.receipt_service import receipt_service
from app.features.time_records.time_record_change_service import time_record_change_service
from app.features.time_records.time_record_exceptions import (
    InvalidReceiptIdError,
    ManualPunchUnauthorizedError,
    ReceiptAccessDeniedError,
    TimeRecordAccessDeniedError,
    TimeRecordNotFoundError,
    TimeRecordUserNotFoundError,
)
from app.features.time_records.time_record_admin_service import TimeRecordAdminService
from app.features.time_records.time_record_models import (
    TimeRecord,
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
    RecordType,
    UserRole,
)
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
        self.admin_service = TimeRecordAdminService(db=db, repo=repo)

    @property
    def repo(self) -> AsyncTimeRecordRepository:
        return self._repo if self._repo is not None else async_time_record_repository


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


    async def _register_manual_punch(self, session: Any, user_id: int, request: Request, record_type: RecordType) -> TimeRecord:
        await self._validate_manual_punch_permission(session, user_id, request)
        current_time, used_ntp = trusted_time_service.get_trusted_time()
        ip_address = get_client_ip(request)
        device_name = get_client_device_name(ip_address, request)
        platform = request.headers.get("X-Platform", "desktop").lower()

        await time_record_change_service.validate_period_open(session, current_time.date())

        if hasattr(session, "sync_session"):
            record = await self.repo.create(
                session, user_id=user_id, record_type=record_type,
                record_datetime=current_time, ip_address=ip_address,
                device_name=device_name, platform=platform,
            )
        else:
            record = time_record_repository.create(
                session, user_id=user_id, record_type=record_type,
                record_datetime=current_time, ip_address=ip_address,
                device_name=device_name, platform=platform,
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

    async def register_entry(self, db: Any | None = None, user_id: int = 0,
                             request: Request | None = None,
                             background_tasks: BackgroundTasks | None = None) -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert request is not None
        record = await self._register_manual_punch(session, user_id, request, RecordType.ENTRY)
        if background_tasks is not None:
            await self.trigger_auto_print(record=record, background_tasks=background_tasks)
        return record

    async def register_exit(self, db: Any | None = None, user_id: int = 0,
                            request: Request | None = None,
                            background_tasks: BackgroundTasks | None = None) -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert request is not None
        record = await self._register_manual_punch(session, user_id, request, RecordType.EXIT)
        if background_tasks is not None:
            await self.trigger_auto_print(record=record, background_tasks=background_tasks)
        return record

    async def _process_toggle_invalidations(self, db: Any, record: TimeRecord, new_type: RecordType):
        previous_type = record.record_type
        target_date = record.record_datetime.date()

        if previous_type == RecordType.ENTRY:
            if await time_record_change_service.is_first_entry_affected(
                db, record.user_id, target_date, record_id=record.id
            ):
                await time_record_change_service.invalidate_pending_extra_time_requests(
                    db, record.user_id, target_date
                )

        if new_type == RecordType.ENTRY:
            if await time_record_change_service.is_first_entry_affected(
                db, record.user_id, target_date, new_datetime=record.record_datetime
            ):
                await time_record_change_service.invalidate_pending_extra_time_requests(
                    db, record.user_id, target_date
                )


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
                                 current_user: User | None = None,
                                 background_tasks: BackgroundTasks | None = None) -> TimeRecord:
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

        await time_record_change_service.validate_period_open(session, record.record_datetime.date())

        new_type = RecordType.EXIT if record.record_type == RecordType.ENTRY else RecordType.ENTRY
        await self._process_toggle_invalidations(session, record, new_type)

        old_data = serialize_model(record)
        record.is_ignored = True
        new_record = self._create_toggled_record(record, new_type, current_user, is_manager)

        session.add(new_record)
        await self._commit_and_audit_toggle_record(session, current_user.id, old_data, new_record, record)
        return new_record

    async def _commit_and_audit_toggle_record(self, session: Any, user_id: int, old_data: dict, new_record: TimeRecord, record: TimeRecord):
        if hasattr(session, "sync_session"):
            await session.flush()
            session.add(record)
            await session.commit()
            await session.refresh(new_record)
            await audit_service.async_log_change(session, user_id, "TOGGLE_RECORD", old_model=old_data,
                                                 new_model=new_record)
        else:
            session.flush()
            session.add(record)
            session.commit()
            session.refresh(new_record)
            audit_service.log_change(session, user_id, "TOGGLE_RECORD", old_model=old_data,
                                     new_model=new_record)


    async def create_admin_record(
        self, db: Any | None = None, obj_in: TimeRecordCreateAdmin | None = None,
        manager_id: int = 0, ip_address: str = "", device_name: str | None = None,
        platform: str = "WEB_ADMIN", request: Request | None = None,
    ) -> TimeRecord:
        return await self.admin_service.create_admin_record(
            db, obj_in, manager_id, ip_address, device_name, platform, request
        )

    async def update_admin_record(
        self, db: Any | None = None, record_id: int = 0,
        obj_in: TimeRecordUpdate | None = None, manager_id: int = 0,
        ip_address: str | None = None, device_name: str | None = None,
        platform: str | None = None, request: Request | None = None,
    ) -> TimeRecord:
        return await self.admin_service.update_admin_record(
            db, record_id, obj_in, manager_id, ip_address, device_name, platform, request
        )

    async def delete_admin_record(
        self, db: Any | None = None, record_id: int = 0,
        obj_in: TimeRecordDeleteAdmin | None = None, manager_id: int = 0,
        justification: str | None = None, request_body: TimeRecordDeleteAdmin | None = None,
        validate_justification: bool = False,
    ):
        return await self.admin_service.delete_admin_record(
            db, record_id, obj_in, manager_id, justification, request_body, validate_justification
        )

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
                     biometric_id: int | None = None, platform: str = "desktop",
                     device_name: str | None = None) -> TimeRecord:
        session = db if db is not None else self.db
        assert session is not None
        assert timestamp is not None
        record_type = await self._determine_punch_type(session, user_id, timestamp)
        if not device_name:
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
        data = receipt_service.build_receipt_data(record, company, short_id, for_print=True)
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

        data = receipt_service.build_receipt_data(record, company, short_id)

        pdf_bytes = receipt_service.generate_pdf_receipt(data)
        filename = f"{record.id}.pdf"
        return pdf_bytes, filename


time_record_service = TimeRecordService()
