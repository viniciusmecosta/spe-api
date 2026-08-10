from datetime import datetime, timedelta, time
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.security import get_client_device_name, get_client_ip
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus, AdjustmentType, RecordType, UserRole
from app.domain.models.time_record import TimeRecord, get_local_time
from app.domain.models.user import User
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.time_record import TimeRecordCreateAdmin, TimeRecordDeleteAdmin, TimeRecordUpdate
from app.services.audit_service import audit_service
from app.services.payroll_service import payroll_service
from app.services.trusted_time_service import trusted_time_service


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
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Registro manual não autorizado para este dispositivo. Utilize a biometria ou solicite liberação ao gestor.")

    def register_entry(self, db: Session, user_id: int, request: Request) -> TimeRecord:
        self._validate_manual_punch_permission(db, user_id, request)
        current_time, used_ntp = trusted_time_service.get_trusted_time()
        ip_address = get_client_ip(request)
        device_name = get_client_device_name(ip_address, request)
        platform = request.headers.get("X-Platform", "desktop").lower()
        payroll_service.validate_period_open(db, current_time.date())
        record = time_record_repository.create(db, user_id, RecordType.ENTRY, current_time, ip_address, device_name,
                                               platform=platform)
        if not used_ntp:
            request.state.ntp_error = True
            record.edit_justification = "Registro feito com a hora local do servidor (Falha no NTP)."
            db.add(record)
            db.commit()
            db.refresh(record)
            audit_service.log(db, user_id=user_id, action="NTP_FALLBACK", entity="TIME_RECORD", entity_id=record.id,
                              new_data={"justification": record.edit_justification})
        return record

    def register_exit(self, db: Session, user_id: int, request: Request) -> TimeRecord:
        self._validate_manual_punch_permission(db, user_id, request)
        current_time, used_ntp = trusted_time_service.get_trusted_time()
        ip_address = get_client_ip(request)
        device_name = get_client_device_name(ip_address, request)
        platform = request.headers.get("X-Platform", "desktop").lower()
        payroll_service.validate_period_open(db, current_time.date())
        record = time_record_repository.create(db, user_id, RecordType.EXIT, current_time, ip_address, device_name,
                                               platform=platform)
        if not used_ntp:
            request.state.ntp_error = True
            record.edit_justification = "Registro feito com a hora local do servidor (Falha no NTP)."
            db.add(record)
            db.commit()
            db.refresh(record)
            audit_service.log(db, user_id=user_id, action="NTP_FALLBACK", entity="TIME_RECORD", entity_id=record.id,
                              new_data={"justification": record.edit_justification})
        return record

    def toggle_record_type(self, db: Session, record_id: int, current_user: User) -> TimeRecord:
        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de ponto não encontrado.")
        is_owner = record.user_id == current_user.id
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if not is_owner and (not is_manager):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
        payroll_service.validate_period_open(db, record.record_datetime.date())
        previous_type = record.record_type
        new_type = RecordType.EXIT if previous_type == RecordType.ENTRY else RecordType.ENTRY
        if previous_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, record.user_id, record.record_datetime.date(), record_id=record.id):
                self._invalidate_extra_time_requests(db, record.user_id, record.record_datetime.date())
        if new_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, record.user_id, record.record_datetime.date(), new_datetime=record.record_datetime):
                self._invalidate_extra_time_requests(db, record.user_id, record.record_datetime.date())
        record.is_ignored = True
        new_record = TimeRecord(user_id=record.user_id, record_type=new_type, record_datetime=record.record_datetime,
                                ip_address=record.ip_address, device_name=record.device_name, platform=record.platform,
                                biometric_id=record.biometric_id, edited_by=current_user.id,
                                edit_justification="Inversão de marcação efetuada",
                                original_record_id=record.original_record_id if record.original_record_id else record.id,
                                created_at=record.created_at, is_verified=True if is_manager else False)
        db.add(new_record)
        db.flush()
        db.add(record)
        db.commit()
        db.refresh(new_record)
        audit_service.log(db, user_id=current_user.id, action="TOGGLE_RECORD", entity="TIME_RECORD",
                          entity_id=new_record.id, old_data={"record_type": previous_type.value},
                          new_data={"record_type": new_type.value})
        return new_record

    def create_admin_record(self, db: Session, obj_in: TimeRecordCreateAdmin, manager_id: int, ip_address: str,
                            device_name: str | None, platform: str = "WEB_ADMIN") -> TimeRecord:
        payroll_service.validate_period_open(db, obj_in.record_datetime.date())
        if obj_in.record_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, obj_in.user_id, obj_in.record_datetime.date(), new_datetime=obj_in.record_datetime):
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
        justification_val = obj_in.edit_justification if obj_in.edit_justification else ""
        audit_service.log(db, user_id=manager_id, action="CREATE_RECORD_ADMIN", entity="TIME_RECORD",
                          entity_id=record.id,
                          new_data={"record_time": str(obj_in.record_datetime), "record_type": obj_in.record_type.value,
                                    "justification": justification_val})
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

    def _log_admin_update_audit(self, db: Session, manager_id: int, new_record: TimeRecord, old_data: dict):
        justification_val = new_record.edit_justification if new_record.edit_justification else ""
        new_data_raw = {"record_type": new_record.record_type.value, "record_time": str(new_record.record_datetime),
                        "justification": justification_val}
        actual_old, actual_new = audit_service.compute_diffs(old_data, new_data_raw)
        audit_service.log(db, user_id=manager_id, action="UPDATE_RECORD_ADMIN", entity="TIME_RECORD",
                          entity_id=new_record.id, old_data=actual_old, new_data=actual_new)

    def update_admin_record(self, db: Session, record_id: int, obj_in: TimeRecordUpdate, manager_id: int,
                            ip_address: str | None = None, device_name: str | None = None,
                            platform: str | None = None) -> TimeRecord:
        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
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

        old_data = {"record_type": record.record_type.value, "record_time": str(record.record_datetime),
                    "justification": record.edit_justification if record.edit_justification else ""}

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
        self._log_admin_update_audit(db, manager_id, new_record, old_data)
        return new_record

    def delete_admin_record(self, db: Session, record_id: int, obj_in: TimeRecordDeleteAdmin, manager_id: int):
        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
        payroll_service.validate_period_open(db, record.record_datetime.date())
        if record.record_type == RecordType.ENTRY:
            if self._is_first_entry_affected(db, record.user_id, record.record_datetime.date(), record_id=record.id):
                self._invalidate_extra_time_requests(db, record.user_id, record.record_datetime.date())
        justification_val = obj_in.edit_justification if obj_in.edit_justification else ""
        old_data = {"record_type": record.record_type.value, "record_time": str(record.record_datetime)}
        time_record_repository.delete(db, record_id, manager_id)
        audit_service.log(db, user_id=manager_id, action="DELETE_RECORD_ADMIN", entity="TIME_RECORD",
                          entity_id=record_id, old_data=old_data, new_data={"justification": justification_val})

    def create_punch(self, db: Session, user_id: int, timestamp: datetime, ip_address: str,
                     biometric_id: int | None = None, platform: str = "desktop") -> TimeRecord:
        last_record = time_record_repository.get_last_by_user(db, user_id)
        record_type = RecordType.ENTRY
        if last_record and last_record.record_type == RecordType.ENTRY:
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
                record_type = RecordType.EXIT
        device_name = get_client_device_name(ip_address)
        record = time_record_repository.create(db, user_id=user_id, record_type=record_type, record_datetime=timestamp,
                                               ip_address=ip_address, device_name=device_name, platform=platform,
                                               biometric_id=biometric_id)
        return record

    def get_my_records(self, db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[TimeRecord]:
        return time_record_repository.get_all_by_user(db, user_id, skip, limit)

    def list_records_for_admin(self, db: Session, user_id: int, start_date: datetime, end_date: datetime) -> list[TimeRecord]:
        return time_record_repository.get_by_range(db, user_id, start_date, end_date)

    def get_record_timeline(self, db: Session, record_id: int) -> list[TimeRecord]:
        return time_record_repository.get_timeline(db, record_id)

    def trigger_auto_print(self, db: Session, record: TimeRecord, background_tasks):
        from app.repositories.company_repository import company_repository
        from app.repositories.printer_repository import printer_repository
        from app.services.hashid_service import hashid_service
        from app.services.receipt_service import receipt_service

        company = company_repository.get_current(db)
        if not company:
            return

        user_auto_print = record.user.auto_print_receipt
        should_print = user_auto_print if user_auto_print is not None else company.auto_print_receipt

        if should_print and company.default_printer_id:
            printer = printer_repository.get_by_id(db, company.default_printer_id)
            if printer and printer.status:
                short_id = hashid_service.encode(record.id)
                data = {
                    "company_name": company.name,
                    "company_cnpj": company.cnpj,
                    "employee_name": record.user.name,
                    "employee_cpf": record.user.cpf,
                    "employee_pis": record.user.pis,
                    "record_datetime": record.record_datetime.strftime("%d/%m/%Y %H:%M:%S"),
                    "device_name": record.device_name or "Desconhecido",
                    "nsr": record.id,
                    "short_id": short_id
                }
                background_tasks.add_task(receipt_service.print_receipt_async, printer, data)

    def get_receipt_data(self, db: Session, short_id: str, current_user: User) -> dict:
        from app.repositories.company_repository import company_repository
        from app.services.hashid_service import hashid_service

        record_id = hashid_service.decode(short_id)
        if not record_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid receipt ID")

        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

        if current_user.role == UserRole.EMPLOYEE and record.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to view this receipt")

        company = company_repository.get_current(db)
        timeline = self.get_record_timeline(db, record.id)

        return {
            "short_id": short_id,
            "record_id": record.id,
            "company_name": company.name if company else "N/A",
            "company_cnpj": company.cnpj if company else "N/A",
            "employee_name": record.user.name,
            "employee_cpf": record.user.cpf,
            "employee_pis": record.user.pis,
            "record_datetime": record.record_datetime,
            "device_name": record.device_name or "Desconhecido",
            "record_type": record.record_type,
            "timeline": [
                {
                    "action": t.action,
                    "timestamp": t.timestamp,
                    "user_name": t.user.name if t.user else None,
                    "old_data": t.old_data,
                    "new_data": t.new_data
                } for t in timeline
            ] if hasattr(timeline[0], 'action') else []
        }

    def get_receipt_pdf(self, db: Session, short_id: str, current_user: User) -> bytes:
        from app.repositories.company_repository import company_repository
        from app.services.hashid_service import hashid_service
        from app.services.receipt_service import receipt_service

        record_id = hashid_service.decode(short_id)
        if not record_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid receipt ID")

        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

        if current_user.role == UserRole.EMPLOYEE and record.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to view this receipt")

        company = company_repository.get_current(db)

        record_type_str = "Entrada" if record.record_type.name == "ENTRY" else "Saída"
        date_str = record.record_datetime.strftime("%d/%m/%Y")
        time_str = record.record_datetime.strftime("%H:%M:%S")

        def mask_cnpj(c: str) -> str:
            if not c or len(c) != 14: return c
            return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

        def mask_cpf(c: str) -> str:
            if not c or len(c) != 11: return c
            return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"

        data = {
            "company_name": company.name if company else "N/A",
            "company_cnpj": mask_cnpj(company.cnpj) if company else "N/A",
            "employee_name": record.user.name,
            "employee_cpf": mask_cpf(record.user.cpf),
            "employee_pis": record.user.pis,
            "record_date": date_str,
            "record_time": time_str,
            "record_type_str": record_type_str,
            "device_name": record.device_name or "Desconhecido",
            "nsr": record.id,
            "short_id": short_id.upper()
        }

        return receipt_service.generate_pdf_receipt(data)

time_record_service = TimeRecordService()