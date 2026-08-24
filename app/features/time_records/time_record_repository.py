from datetime import datetime

from sqlalchemy import and_, desc, distinct, func, or_
from sqlalchemy.orm import Session, selectinload

from app.features.time_records.time_record_models import (
    TimeRecord,
    get_local_time,
)
from app.features.time_records.time_record_schemas import TimeRecordUpdate
from app.shared.enums import RecordType


class TimeRecordRepository:
    def create(self, db: Session, user_id: int, record_type: RecordType, record_datetime: datetime,
               ip_address: str | None = None, device_name: str | None = None, platform: str | None = None,
               biometric_id: int | None = None) -> TimeRecord:
        db_record = TimeRecord(
            user_id=user_id,
            record_type=record_type,
            record_datetime=record_datetime,
            ip_address=ip_address,
            device_name=device_name,
            platform=platform,
            biometric_id=biometric_id
        )
        db.add(db_record)
        db.commit()
        db.refresh(db_record)
        return db_record

    def get(self, db: Session, record_id: int) -> TimeRecord | None:
        return db.query(TimeRecord).options(
            selectinload(TimeRecord.user),
            selectinload(TimeRecord.editor)
        ).filter(
            TimeRecord.id == record_id,
            TimeRecord.is_ignored == False
        ).first()

    def get_last_by_user(self, db: Session, user_id: int) -> TimeRecord | None:
        return db.query(TimeRecord).options(
            selectinload(TimeRecord.user),
            selectinload(TimeRecord.editor)
        ).filter(
            TimeRecord.user_id == user_id,
            TimeRecord.is_ignored == False
        ).order_by(desc(TimeRecord.record_datetime)).first()

    def get_all_by_user(self, db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[TimeRecord]:
        return db.query(TimeRecord).options(
            selectinload(TimeRecord.user),
            selectinload(TimeRecord.editor)
        ).filter(
            TimeRecord.user_id == user_id,
            TimeRecord.is_ignored == False
        ).order_by(desc(TimeRecord.record_datetime)).offset(skip).limit(limit).all()

    def get_by_range(self, db: Session, user_id: int, start_date: datetime, end_date: datetime) -> list[TimeRecord]:
        return db.query(TimeRecord).options(
            selectinload(TimeRecord.user),
            selectinload(TimeRecord.editor)
        ).filter(
            and_(
                TimeRecord.user_id == user_id,
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date,
                TimeRecord.is_ignored == False
            )
        ).order_by(TimeRecord.record_datetime).all()

    def get_by_users_and_range(self, db: Session, user_ids: list[int], start_date: datetime, end_date: datetime) -> \
    list[TimeRecord]:
        return db.query(TimeRecord).options(
            selectinload(TimeRecord.user),
            selectinload(TimeRecord.editor)
        ).filter(
            and_(
                TimeRecord.user_id.in_(user_ids),
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date,
                TimeRecord.is_ignored == False
            )
        ).order_by(TimeRecord.record_datetime).all()

    def count_unique_users_in_range(self, db: Session, start_date: datetime, end_date: datetime) -> int:
        return db.query(func.count(distinct(TimeRecord.user_id))).filter(
            and_(
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date,
                TimeRecord.is_ignored == False
            )
        ).scalar() or 0

    def count_records_in_range(self, db: Session, start_date: datetime, end_date: datetime) -> int:
        return db.query(TimeRecord).filter(
            and_(
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date,
                TimeRecord.is_ignored == False
            )
        ).count()

    def update(self, db: Session, db_obj: TimeRecord, obj_in: TimeRecordUpdate) -> TimeRecord:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, record_id: int, manager_id: int):
        record = db.query(TimeRecord).filter(
            TimeRecord.id == record_id,
            TimeRecord.is_ignored == False
        ).first()
        if record:
            record.deleted_at = get_local_time()
            record.deleted_by = manager_id
            record.is_ignored = True
            db.commit()

    def get_timeline(self, db: Session, record_id: int) -> list[TimeRecord]:
        record = db.query(TimeRecord).filter(TimeRecord.id == record_id).first()
        if not record:
            return []

        anchor_id = record.original_record_id if record.original_record_id else record.id

        return db.query(TimeRecord).options(
            selectinload(TimeRecord.user),
            selectinload(TimeRecord.editor)
        ).filter(
            or_(
                TimeRecord.id == anchor_id,
                TimeRecord.original_record_id == anchor_id
            )
        ).order_by(TimeRecord.id.desc()).all()


time_record_repository = TimeRecordRepository()
