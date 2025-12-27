from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.domain.models.time_record import TimeRecord
from app.domain.models.enums import RecordType
from datetime import datetime

class TimeRecordRepository:
    def create(self, db: Session, user_id: int, record_type: RecordType, record_datetime: datetime, ip_address: str = None) -> TimeRecord:
        db_record = TimeRecord(
            user_id=user_id,
            record_type=record_type,
            record_datetime=record_datetime,
            ip_address=ip_address
        )
        db.add(db_record)
        db.commit()
        db.refresh(db_record)
        return db_record

    def get_last_by_user(self, db: Session, user_id: int) -> TimeRecord | None:
        return db.query(TimeRecord).filter(TimeRecord.user_id == user_id).order_by(desc(TimeRecord.record_datetime)).first()

    def get_all_by_user(self, db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[TimeRecord]:
        return db.query(TimeRecord).filter(TimeRecord.user_id == user_id).order_by(desc(TimeRecord.record_datetime)).offset(skip).limit(limit).all()

time_record_repository = TimeRecordRepository()