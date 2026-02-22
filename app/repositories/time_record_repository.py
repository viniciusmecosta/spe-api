from datetime import datetime
from sqlalchemy import desc, and_, distinct, func
from sqlalchemy.orm import Session
from typing import List

from app.domain.models.enums import RecordType
from app.domain.models.time_record import TimeRecord
from app.schemas.time_record import TimeRecordUpdate


class TimeRecordRepository:
    def create(self, db: Session, user_id: int, record_type: RecordType, record_datetime: datetime,
               ip_address: str = None, is_time_verified: bool = False) -> TimeRecord:
        db_record = TimeRecord(
            user_id=user_id,
            record_type=record_type,
            record_datetime=record_datetime,
            ip_address=ip_address,
            is_time_verified=is_time_verified
        )
        db.add(db_record)
        db.commit()
        db.refresh(db_record)
        return db_record

    def get(self, db: Session, record_id: int) -> TimeRecord | None:
        return db.query(TimeRecord).filter(TimeRecord.id == record_id).first()

    def get_last_by_user(self, db: Session, user_id: int) -> TimeRecord | None:
        return db.query(TimeRecord).filter(TimeRecord.user_id == user_id).order_by(
            desc(TimeRecord.record_datetime)).first()

    def get_all_by_user(self, db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[TimeRecord]:
        return db.query(TimeRecord).filter(TimeRecord.user_id == user_id).order_by(
            desc(TimeRecord.record_datetime)).offset(skip).limit(limit).all()

    def get_by_range(self, db: Session, user_id: int, start_date: datetime, end_date: datetime) -> list[TimeRecord]:
        return db.query(TimeRecord).filter(
            and_(
                TimeRecord.user_id == user_id,
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date
            )
        ).order_by(TimeRecord.record_datetime).all()

    def get_by_users_and_range(self, db: Session, user_ids: List[int], start_date: datetime, end_date: datetime) -> \
            List[TimeRecord]:
        return db.query(TimeRecord).filter(
            and_(
                TimeRecord.user_id.in_(user_ids),
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date
            )
        ).order_by(TimeRecord.record_datetime).all()

    def count_unique_users_in_range(self, db: Session, start_date: datetime, end_date: datetime) -> int:
        return db.query(func.count(distinct(TimeRecord.user_id))).filter(
            and_(
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date
            )
        ).scalar()

    def update(self, db: Session, db_obj: TimeRecord, obj_in: TimeRecordUpdate) -> TimeRecord:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, record_id: int):
        db.query(TimeRecord).filter(TimeRecord.id == record_id).delete()
        db.commit()


time_record_repository = TimeRecordRepository()
