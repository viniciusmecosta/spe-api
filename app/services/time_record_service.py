import ntplib
import pytz
from datetime import datetime
from fastapi import HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_client_ip
from app.domain.models.enums import RecordType, UserRole
from app.domain.models.time_record import TimeRecord, ManualAdjustment
from app.domain.models.user import User
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.time_record import TimeRecordUpdate, TimeRecordCreateAdmin, TimeRecordDeleteAdmin
from app.services.audit_service import audit_service
from app.services.manual_auth_service import manual_auth_service
from app.services.payroll_service import payroll_service


class TimeRecordService:
    def _get_trusted_time(self):
        tz = pytz.timezone(settings.TIMEZONE)
        try:
            client = ntplib.NTPClient()
            response = client.request('pool.ntp.org', version=3, timeout=2)
            utc_time = datetime.fromtimestamp(response.tx_time, pytz.utc)
            return utc_time.astimezone(tz), True
        except Exception:
            return datetime.now(tz), False

    def _validate_manual_punch_permission(self, db: Session, user_id: int):
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.role in [UserRole.MANAGER, UserRole.MAINTAINER]:
            return

        if user.can_manual_punch:
            return

        if manual_auth_service.check_authorization(db, user_id):
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registro manual não autorizado. Utilize a biometria ou solicite liberação ao gestor."
        )

    def register_entry(self, db: Session, user_id: int, request: Request) -> TimeRecord:
        self._validate_manual_punch_permission(db, user_id)

        current_time, is_verified = self._get_trusted_time()
        ip_address = get_client_ip(request)
        payroll_service.validate_period_open(db, current_time.date())

        return time_record_repository.create(
            db, user_id, RecordType.ENTRY, current_time, ip_address, is_time_verified=is_verified
        )

    def register_exit(self, db: Session, user_id: int, request: Request) -> TimeRecord:
        self._validate_manual_punch_permission(db, user_id)

        current_time, is_verified = self._get_trusted_time()
        ip_address = get_client_ip(request)
        payroll_service.validate_period_open(db, current_time.date())

        return time_record_repository.create(
            db, user_id, RecordType.EXIT, current_time, ip_address, is_time_verified=is_verified
        )

    def toggle_record_type(self, db: Session, record_id: int, current_user: User) -> TimeRecord:
        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time record not found")

        is_owner = record.user_id == current_user.id
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]

        if not is_owner and not is_manager:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

        payroll_service.validate_period_open(db, record.record_datetime.date())

        previous_type = record.record_type
        new_type = RecordType.EXIT if previous_type == RecordType.ENTRY else RecordType.ENTRY
        record.record_type = new_type

        adjustment = ManualAdjustment(
            time_record_id=record.id,
            previous_type=previous_type,
            new_type=new_type,
            adjusted_by_user_id=current_user.id
        )

        db.add(adjustment)
        db.add(record)
        db.commit()
        db.refresh(record)

        audit_service.log(
            db,
            actor_id=current_user.id,
            target_user_id=record.user_id,
            action="TOGGLE_RECORD",
            entity="TIME_RECORD",
            entity_id=record.id,
            old_data={"record_type": previous_type.value},
            new_data={"record_type": new_type.value}
        )
        return record

    def create_admin_record(self, db: Session, obj_in: TimeRecordCreateAdmin, manager_id: int,
                            ip_address: str) -> TimeRecord:
        payroll_service.validate_period_open(db, obj_in.record_datetime.date())
        record = time_record_repository.create(
            db, user_id=obj_in.user_id, record_type=obj_in.record_type,
            record_datetime=obj_in.record_datetime, ip_address=ip_address, is_time_verified=True
        )
        record.is_manual = True
        record.edited_by = manager_id
        record.edit_justification = obj_in.edit_justification
        record.edit_reason = obj_in.edit_reason
        db.add(record)
        db.commit()
        db.refresh(record)

        justification_val = obj_in.edit_justification.value if obj_in.edit_justification else ""

        audit_service.log(
            db,
            actor_id=manager_id,
            target_user_id=obj_in.user_id,
            action="CREATE_RECORD_ADMIN",
            entity="TIME_RECORD",
            entity_id=record.id,
            new_data={
                "record_time": str(obj_in.record_datetime),
                "record_type": obj_in.record_type.value,
                "justification": justification_val,
                "reason": obj_in.edit_reason
            }
        )
        return record

    def update_admin_record(self, db: Session, record_id: int, obj_in: TimeRecordUpdate, manager_id: int) -> TimeRecord:
        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        payroll_service.validate_period_open(db, record.record_datetime.date())
        if obj_in.record_datetime:
            payroll_service.validate_period_open(db, obj_in.record_datetime.date())

        if not record.original_timestamp:
            record.original_timestamp = record.record_datetime

        employee_id = record.user_id

        old_data = {
            "record_type": record.record_type.value,
            "record_time": str(record.record_datetime)
        }

        updated = time_record_repository.update(db, record, obj_in)
        updated.is_manual = True
        updated.edited_by = manager_id
        db.add(updated)
        db.commit()
        db.refresh(updated)

        justification_val = updated.edit_justification.value if updated.edit_justification else ""

        audit_service.log(
            db,
            actor_id=manager_id,
            target_user_id=employee_id,
            action="UPDATE_RECORD_ADMIN",
            entity="TIME_RECORD",
            entity_id=record.id,
            old_data=old_data,
            new_data={
                "record_type": updated.record_type.value,
                "record_time": str(updated.record_datetime),
                "justification": justification_val,
                "reason": updated.edit_reason
            }
        )
        return updated

    def delete_admin_record(self, db: Session, record_id: int, obj_in: TimeRecordDeleteAdmin, manager_id: int):
        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        payroll_service.validate_period_open(db, record.record_datetime.date())

        target_id = record.user_id
        justification_val = obj_in.edit_justification.value if obj_in.edit_justification else ""

        old_data = {
            "record_type": record.record_type.value,
            "record_time": str(record.record_datetime)
        }

        time_record_repository.delete(db, record_id)

        audit_service.log(
            db,
            actor_id=manager_id,
            target_user_id=target_id,
            action="DELETE_RECORD_ADMIN",
            entity="TIME_RECORD",
            entity_id=record_id,
            old_data=old_data,
            new_data={
                "justification": justification_val,
                "reason": obj_in.edit_reason
            }
        )

    def create_punch(self, db: Session, user_id: int, timestamp: datetime, ip_address: str,
                     biometric_id: int = None) -> TimeRecord:
        last_record = time_record_repository.get_last_by_user(db, user_id)

        record_type = RecordType.ENTRY
        if last_record and last_record.record_type == RecordType.ENTRY:
            tz = pytz.timezone(settings.TIMEZONE)

            last_time = last_record.record_datetime
            if last_time.tzinfo is None:
                last_time = pytz.utc.localize(last_time)
            last_local_date = last_time.astimezone(tz).date()

            curr_time = timestamp
            if curr_time.tzinfo is None:
                curr_time = pytz.utc.localize(curr_time)
            curr_local_date = curr_time.astimezone(tz).date()

            if last_local_date == curr_local_date:
                record_type = RecordType.EXIT

        return time_record_repository.create(
            db,
            user_id=user_id,
            record_type=record_type,
            record_datetime=timestamp,
            ip_address=ip_address,
            is_time_verified=True,
            biometric_id=biometric_id
        )


time_record_service = TimeRecordService()
