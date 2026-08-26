from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, distinct, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database.repository import BaseRepository
from app.features.time_records.time_record_models import (
    TimeRecord,
    get_local_time,
)
from app.features.time_records.time_record_schemas import (
    TimeRecordCreate,
    TimeRecordUpdate,
)
from app.shared.enums import RecordType


class TimeRecordRepository(BaseRepository[TimeRecord, TimeRecordCreate, TimeRecordUpdate]):
    def __init__(self):
        super().__init__(TimeRecord)

    def create(
        self,
        db: Session,
            *,
            obj_in: TimeRecordCreate | None = None,
            user_id: int | None = None,
            record_type: RecordType | None = None,
            record_datetime: datetime | None = None,
        ip_address: str | None = None,
        device_name: str | None = None,
        platform: str | None = None,
        biometric_id: int | None = None,
    ) -> TimeRecord:
        if obj_in is not None:
            return super().create(db, obj_in=obj_in)
        db_record = TimeRecord(
            user_id=user_id,
            record_type=record_type,
            record_datetime=record_datetime,
            ip_address=ip_address,
            device_name=device_name,
            platform=platform,
            biometric_id=biometric_id,
        )
        db.add(db_record)
        db.commit()
        db.refresh(db_record)
        return db_record

    def get(self, db: Session, record_id: int) -> TimeRecord | None:
        stmt = (
            select(TimeRecord)
            .options(
                selectinload(TimeRecord.user),
                selectinload(TimeRecord.editor),
            )
            .where(
                TimeRecord.id == record_id,
                TimeRecord.is_ignored == False,
            )
        )
        return db.scalars(stmt).first()

    def get_last_by_user(self, db: Session, user_id: int) -> TimeRecord | None:
        stmt = (
            select(TimeRecord)
            .options(
                selectinload(TimeRecord.user),
                selectinload(TimeRecord.editor),
            )
            .where(
                TimeRecord.user_id == user_id,
                TimeRecord.is_ignored == False,
            )
            .order_by(desc(TimeRecord.record_datetime))
        )
        return db.scalars(stmt).first()

    def get_all_by_user(
        self, db: Session, user_id: int, skip: int = 0, limit: int = 100
    ) -> list[TimeRecord]:
        stmt = (
            select(TimeRecord)
            .options(
                selectinload(TimeRecord.user),
                selectinload(TimeRecord.editor),
            )
            .where(
                TimeRecord.user_id == user_id,
                TimeRecord.is_ignored == False,
            )
            .order_by(desc(TimeRecord.record_datetime))
            .offset(skip)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    def get_by_range(
        self, db: Session, user_id: int, start_date: datetime, end_date: datetime
    ) -> list[TimeRecord]:
        stmt = (
            select(TimeRecord)
            .options(
                selectinload(TimeRecord.user),
                selectinload(TimeRecord.editor),
            )
            .where(
                and_(
                    TimeRecord.user_id == user_id,
                    TimeRecord.record_datetime >= start_date,
                    TimeRecord.record_datetime <= end_date,
                    TimeRecord.is_ignored == False,
                )
            )
            .order_by(TimeRecord.record_datetime)
        )
        return list(db.scalars(stmt).all())

    def get_by_users_and_range(
        self, db: Session, user_ids: list[int], start_date: datetime, end_date: datetime
    ) -> list[TimeRecord]:
        stmt = (
            select(TimeRecord)
            .options(
                selectinload(TimeRecord.user),
                selectinload(TimeRecord.editor),
            )
            .where(
                and_(
                    TimeRecord.user_id.in_(user_ids),
                    TimeRecord.record_datetime >= start_date,
                    TimeRecord.record_datetime <= end_date,
                    TimeRecord.is_ignored == False,
                )
            )
            .order_by(TimeRecord.record_datetime)
        )
        return list(db.scalars(stmt).all())

    def count_unique_users_in_range(
        self, db: Session, start_date: datetime, end_date: datetime
    ) -> int:
        stmt = select(func.count(distinct(TimeRecord.user_id))).where(
            and_(
                TimeRecord.record_datetime >= start_date,
                TimeRecord.record_datetime <= end_date,
                TimeRecord.is_ignored == False,
            )
        )
        return db.scalar(stmt) or 0

    def count_records_in_range(
        self, db: Session, start_date: datetime, end_date: datetime
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(TimeRecord)
            .where(
                and_(
                    TimeRecord.record_datetime >= start_date,
                    TimeRecord.record_datetime <= end_date,
                    TimeRecord.is_ignored == False,
                )
            )
        )
        return db.scalar(stmt) or 0

    def update(
            self, db: Session, *, db_obj: TimeRecord, obj_in: TimeRecordUpdate | dict[str, Any]
    ) -> TimeRecord:
        return super().update(db, db_obj=db_obj, obj_in=obj_in)

    def delete(self, db: Session, record_id: int, manager_id: int):
        stmt = select(TimeRecord).where(
            TimeRecord.id == record_id,
            TimeRecord.is_ignored == False,
        )
        record = db.scalars(stmt).first()
        if record:
            record.deleted_at = get_local_time()
            record.deleted_by = manager_id
            record.is_ignored = True
            db.commit()

    def get_timeline(self, db: Session, record_id: int) -> list[TimeRecord]:
        stmt = select(TimeRecord).where(TimeRecord.id == record_id)
        record = db.scalars(stmt).first()
        if not record:
            return []

        anchor_id = record.original_record_id if record.original_record_id else record.id

        timeline_stmt = (
            select(TimeRecord)
            .options(
                selectinload(TimeRecord.user),
                selectinload(TimeRecord.editor),
            )
            .where(
                or_(
                    TimeRecord.id == anchor_id,
                    TimeRecord.original_record_id == anchor_id,
                )
            )
            .order_by(TimeRecord.id.desc())
        )
        return list(db.scalars(timeline_stmt).all())


time_record_repository = TimeRecordRepository()
