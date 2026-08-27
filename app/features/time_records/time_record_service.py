from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_client_device_name, get_client_ip
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.companies.company_repository import company_repository
from app.features.payroll.payroll_service import payroll_service
from app.features.printers.printer_repository import printer_repository
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
from app.features.users.user_repository import user_repository
from app.shared.enums import (
    AdjustmentStatus,
    AdjustmentType,
    RecordType,
    UserRole,
)
from app.shared.hashid_service import hashid_service
from app.shared.trusted_time_service import trusted_time_service
from app.utils.formatters import mask_cnpj, mask_cpf


class TimeRecordService:

    def _invalidate_extra_time_requests(self, db: Session, user_id: int, target_date: datetime.date):
        requests = db.query(AdjustmentRequest).filter(AdjustmentRequest.user_id == user_id,
                                                      AdjustmentRequest.target_date == target_date,
                                                      AdjustmentRequest.adjustment_type == AdjustmentType.EXTRA_TIME,
                                                      AdjustmentRequest.status == AdjustmentStatus.PENDING).all()
        for req in requests:
            db.delete(req)
        db.flush()

    def _is_first_entry_affected(self, db: Session, user_id: int, target_date: datetime.date,
                                 record_id: int | None = None, new_datetime: datetime | None = None) -> bool:
        start_of_day = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(settings.TIMEZONE))
        end_of_day = datetime.combine(target_date, time.max, tzinfo=ZoneInfo(settings.TIMEZONE))
        first_entry = (db.query(TimeRecord).filter(TimeRecord.user_id == user_id,
                                                   TimeRecord.record_type == RecordType.ENTRY,
                                                   TimeRecord.deleted_at.is_(None),
                                                   TimeRecord.record_datetime >= start_of_day,
                                                   TimeRecord.record_datetime <= end_of_day)
                       .order_by(TimeRecord.record_datetime.asc()).first())
        if not first_entry:
            return new_datetime is not None
        if record_id is not None and first_entry.id == record_id:
            return True
        if new_datetime is not None:
            if new_datetime <= first_entry.record_datetime:
                return True
        return False

    def _validate_manual_punch_permission(self, db: Session, user_id: int, request: Request):
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

    def register_entry(self, db: Session, user_id: int, request: Request) -> TimeRecord:
        self._validate_manual_punch_permission(db, user_id, request)
        current_time, used_ntp = trusted_time_service.get_trusted_time()
        ip_address = get_client_ip(request)
        device_name = get_client_device_name(ip_address, request)
        platform = request.headers.get("X-Platform", "desktop").lower()
        payroll_service.validate_period_open(db, current_time.date())
        record = time_record_repository.create(
            db,
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
            db.add(record)
            db.commit()
            db.refresh(record)
            audit_service.log_change(db, user_id, "NTP_FALLBACK", entity="TIME_RECORD", entity_id=record.id,
                                     new_data={"justification": record.edit_justification})
        return record

    def register_exit(self, db: Session, user_id: int, request: Request) -> TimeRecord:
        self._validate_manual_punch_permission(db, user_id, request)
        current_time, used_ntp = trusted_time_service.get_trusted_time()
        ip_address = get_client_ip(request)
        device_name = get_client_device_name(ip_address, request)
        platform = request.headers.get("X-Platform", "desktop").lower()
        payroll_service.validate_period_open(db, current_time.date())
        record = time_record_repository.create(
            db,
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
            db.add(record)
            db.commit()
            db.refresh(record)
            audit_service.log_change(db, user_id, "NTP_FALLBACK", entity="TIME_RECORD", entity_id=record.id,
                                     new_data={"justification": record.edit_justification})
        return record

    def _process_toggle_invalidations(self, db: Session, record: TimeRecord, new_type: RecordType):
        previous_type = record.record_type
        target_date = record.record_datetime.date()

        if previous_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, record.user_id, target_date, record_id=record.id):
                self._invalidate_extra_time_requests(db, record.user_id, target_date)

        if new_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, record.user_id, target_date, new_datetime=record.record_datetime):
                self._invalidate_extra_time_requests(db, record.user_id, target_date)

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

    def toggle_record_type(self, db: Session, record_id: int, current_user: User) -> TimeRecord:
        record = time_record_repository.get(db, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)

        is_owner = record.user_id == current_user.id
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if not is_owner and not is_manager:
            raise TimeRecordAccessDeniedError()

        payroll_service.validate_period_open(db, record.record_datetime.date())

        new_type = RecordType.EXIT if record.record_type == RecordType.ENTRY else RecordType.ENTRY
        self._process_toggle_invalidations(db, record, new_type)

        old_data = serialize_model(record)
        record.is_ignored = True
        new_record = self._create_toggled_record(record, new_type, current_user, is_manager)

        db.add(new_record)
        db.flush()
        db.add(record)
        db.commit()
        db.refresh(new_record)
        audit_service.log_change(db, current_user.id, "TOGGLE_RECORD", old_model=old_data, new_model=new_record)
        return new_record

    def create_admin_record(self, db: Session, obj_in: TimeRecordCreateAdmin, manager_id: int, ip_address: str,
                            device_name: str | None, platform: str = "WEB_ADMIN") -> TimeRecord:
        payroll_service.validate_period_open(db, obj_in.record_datetime.date())
        if obj_in.record_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, obj_in.user_id, obj_in.record_datetime.date(),
                                             new_datetime=obj_in.record_datetime):
                self._invalidate_extra_time_requests(db, obj_in.user_id, obj_in.record_datetime.date())
        record = time_record_repository.create(db, user_id=obj_in.user_id, record_type=obj_in.record_type,
                                               record_datetime=obj_in.record_datetime, ip_address=ip_address,
                                               device_name=device_name if device_name else "", platform=platform)
        record.edited_by = manager_id
        record.edit_justification = obj_in.edit_justification
        record.is_verified = True
        db.add(record)
        db.commit()
        db.refresh(record)
        audit_service.log_change(db, manager_id, "CREATE_RECORD_ADMIN", new_model=record)
        return record

    def _handle_admin_update_invalidations(self, db: Session, record: TimeRecord, obj_in: TimeRecordUpdate,
                                           old_date: datetime.date, new_date: datetime.date,
                                           new_record_type: RecordType):
        if record.record_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, record.user_id, old_date, record_id=record.id):
                self._invalidate_extra_time_requests(db, record.user_id, old_date)
        if new_record_type == RecordType.ENTRY:
            new_dt = obj_in.record_datetime if obj_in.record_datetime else record.record_datetime
            if self._is_first_entry_affected(db, record.user_id, new_date, record_id=record.id, new_datetime=new_dt):
                self._invalidate_extra_time_requests(db, record.user_id, new_date)

    def update_admin_record(self, db: Session, record_id: int, obj_in: TimeRecordUpdate, manager_id: int,
                            ip_address: str | None = None, device_name: str | None = None,
                            platform: str | None = None) -> TimeRecord:
        record = time_record_repository.get(db, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)
        payroll_service.validate_period_open(db, record.record_datetime.date())
        if obj_in.record_datetime:
            payroll_service.validate_period_open(db, obj_in.record_datetime.date())
        new_record_type = obj_in.record_type if obj_in.record_type else record.record_type
        new_record_datetime = obj_in.record_datetime if obj_in.record_datetime else record.record_datetime
        if new_record_type == record.record_type and new_record_datetime == record.record_datetime:
            return record
        old_date = record.record_datetime.date()
        new_date = obj_in.record_datetime.date() if obj_in.record_datetime else old_date
        self._handle_admin_update_invalidations(db, record, obj_in, old_date, new_date, new_record_type)

        old_data = serialize_model(record)
        record.is_ignored = True
        new_record = TimeRecord(user_id=record.user_id, record_type=new_record_type,
                                record_datetime=new_record_datetime, ip_address=ip_address,
                                device_name=device_name if device_name else "", platform=platform, biometric_id=None,
                                edited_by=manager_id, edit_justification=obj_in.edit_justification,
                                original_record_id=record.original_record_id if record.original_record_id else record.id,
                                created_at=get_local_time(), is_verified=True)
        db.add(new_record)
        db.add(record)
        db.commit()
        db.refresh(new_record)
        audit_service.log_change(db, manager_id, "UPDATE_RECORD_ADMIN", old_model=old_data, new_model=new_record)
        return new_record

    def delete_admin_record(self, db: Session, record_id: int, obj_in: TimeRecordDeleteAdmin, manager_id: int):
        record = time_record_repository.get(db, record_id)
        if not record:
            raise TimeRecordNotFoundError(record_id=record_id)
        payroll_service.validate_period_open(db, record.record_datetime.date())
        if record.record_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, record.user_id, record.record_datetime.date(), record_id=record.id):
                self._invalidate_extra_time_requests(db, record.user_id, record.record_datetime.date())
        justification_val = obj_in.edit_justification if obj_in.edit_justification else ""
        old_data = serialize_model(record)
        time_record_repository.delete(db, record_id, manager_id)
        audit_service.log_change(db, manager_id, "DELETE_RECORD_ADMIN", old_model=old_data,
                                 new_data={"justification": justification_val})

    def _determine_punch_type(self, db: Session, user_id: int, timestamp: datetime) -> RecordType:
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

    def create_punch(self, db: Session, user_id: int, timestamp: datetime, ip_address: str,
                     biometric_id: int | None = None, platform: str = "desktop") -> TimeRecord:
        record_type = self._determine_punch_type(db, user_id, timestamp)
        device_name = get_client_device_name(ip_address)
        return time_record_repository.create(
            db,
            user_id=user_id,
            record_type=record_type,
            record_datetime=timestamp,
            ip_address=ip_address,
            device_name=device_name,
            platform=platform,
            biometric_id=biometric_id,
        )

    def get_my_records(self, db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[TimeRecord]:
        return time_record_repository.get_all_by_user(db, user_id, skip, limit)

    def list_records_for_admin(self, db: Session, user_id: int, start_date: datetime, end_date: datetime) -> list[
        TimeRecord]:
        return time_record_repository.get_by_range(db, user_id, start_date, end_date)

    def get_record_timeline(self, db: Session, record_id: int) -> list[TimeRecord]:
        return time_record_repository.get_timeline(db, record_id)

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

    def trigger_auto_print(self, db: Session, record: TimeRecord, background_tasks):
        company = company_repository.get_current(db)
        if not company or not company.default_printer_id:
            return

        should_print = record.user.auto_print_receipt
        if should_print is None:
            should_print = company.auto_print_receipt

        if not should_print:
            return

        printer = printer_repository.get_by_id(db, company.default_printer_id)
        if not printer or not printer.status:
            return

        short_id = hashid_service.encode(record.id)
        data = self._build_print_data(record, company, short_id)
        background_tasks.add_task(receipt_service.print_receipt_async, printer, data)

    def _get_accessible_record(self, db: Session, short_id: str, current_user: User) -> TimeRecord:
        record_id = hashid_service.decode(short_id)
        if not record_id:
            raise InvalidReceiptIdError(receipt_id=short_id)

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

    def get_receipt_data(self, db: Session, short_id: str, current_user: User):
        record = self._get_accessible_record(db, short_id, current_user)
        company = company_repository.get_current(db)
        timeline = self.get_record_timeline(db, record.id)
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

    def get_receipt_pdf(self, db: Session, short_id: str, current_user: User) -> tuple[bytes, str]:
        record = self._get_accessible_record(db, short_id, current_user)
        company = company_repository.get_current(db)

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
