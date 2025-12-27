from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import pytz
from app.core.config import settings
from app.domain.models.enums import RecordType
from app.repositories.time_record_repository import time_record_repository
from app.domain.models.time_record import TimeRecord, ManualAdjustment


class TimeRecordService:
    def register_entry(self, db: Session, user_id: int, ip_address: str = None) -> TimeRecord:
        last_record = time_record_repository.get_last_by_user(db, user_id)
        if last_record and last_record.record_type == RecordType.ENTRY:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Last record was an entry. You must exit first.")

        tz = pytz.timezone(settings.TIMEZONE)
        current_time = datetime.now(tz)

        return time_record_repository.create(db, user_id, RecordType.ENTRY, current_time, ip_address)

    def register_exit(self, db: Session, user_id: int, ip_address: str = None) -> TimeRecord:
        last_record = time_record_repository.get_last_by_user(db, user_id)
        if not last_record or last_record.record_type == RecordType.EXIT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Last record was an exit (or no record). You must enter first.")

        tz = pytz.timezone(settings.TIMEZONE)
        current_time = datetime.now(tz)

        return time_record_repository.create(db, user_id, RecordType.EXIT, current_time, ip_address)

    def toggle_record_type(self, db: Session, record_id: int, user_id: int) -> TimeRecord:
        record = time_record_repository.get(db, record_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time record not found")

        if record.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this record")

        previous_type = record.record_type
        new_type = RecordType.EXIT if previous_type == RecordType.ENTRY else RecordType.ENTRY

        # Atualiza o registro
        record.record_type = new_type

        # Cria o log de ajuste manual
        adjustment = ManualAdjustment(
            time_record_id=record.id,
            previous_type=previous_type,
            new_type=new_type,
            adjusted_by_user_id=user_id
        )

        db.add(adjustment)
        db.add(record)
        db.commit()
        db.refresh(record)

        return record


time_record_service = TimeRecordService()