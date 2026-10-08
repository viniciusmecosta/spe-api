from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.payroll.payroll_service import payroll_service
from app.features.time_records.time_record_models import TimeRecord
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType


class TimeRecordChangeService:
    async def invalidate_pending_extra_time_requests(
        self, db: Any, user_id: int, target_date: date
    ) -> None:
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

    async def is_first_entry_affected(
        self,
        db: Any,
        user_id: int,
        target_date: date,
        record_id: int | None = None,
        new_datetime: datetime | None = None,
    ) -> bool:
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
            first_entry = db.query(TimeRecord).filter(
                TimeRecord.user_id == user_id,
                TimeRecord.record_type == RecordType.ENTRY,
                TimeRecord.deleted_at.is_(None),
                TimeRecord.record_datetime >= start_of_day,
                TimeRecord.record_datetime <= end_of_day,
            ).order_by(TimeRecord.record_datetime.asc()).first()

        if not first_entry:
            return new_datetime is not None
        if record_id is not None and first_entry.id == record_id:
            return True
        if new_datetime is not None and new_datetime <= first_entry.record_datetime:
            return True
        return False

    async def validate_period_open(self, session: Any, target_date: date) -> None:
        if hasattr(session, "sync_session"):
            await payroll_service.async_validate_period_open(session, target_date)
        else:
            payroll_service.validate_period_open(session, target_date)


time_record_change_service = TimeRecordChangeService()
