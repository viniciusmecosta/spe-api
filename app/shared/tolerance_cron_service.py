import logging
from datetime import date, datetime, time
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.database.session import get_db_session
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import UserWorkScheduleConfig
from app.shared import deps
from app.shared.enums import (
    DayOfWeek,
    RecordType,
)

logger = logging.getLogger(__name__)


class ToleranceCronService:
    def __init__(self, db: Annotated[Any, Depends(deps.get_async_db)] = None):
        self.db = db

    def _process_entry_record(self, db: Session, record: TimeRecord, now: datetime, tz: ZoneInfo):
        if record.user.is_tolerance_exempt:
            record.is_verified = True
            return

        record_date = record.record_datetime.date()

        target_day = DayOfWeek.from_date(record_date)
        config = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.user_id == record.user_id,
            UserWorkScheduleConfig.day_of_week == target_day.value,
            UserWorkScheduleConfig.valid_from <= record_date,
            (UserWorkScheduleConfig.valid_until.is_(None) | (UserWorkScheduleConfig.valid_until >= record_date))
        ).order_by(UserWorkScheduleConfig.valid_from.desc()).first()

        if not config or not config.entry_1:
            record.is_verified = True
            return

        start_of_day = datetime.combine(record_date, time.min, tzinfo=tz)
        end_of_day = datetime.combine(record_date, time.max, tzinfo=tz)

        first_entry = db.query(TimeRecord).filter(
            TimeRecord.user_id == record.user_id,
            TimeRecord.record_type == RecordType.ENTRY,
            TimeRecord.deleted_at.is_(None),
            TimeRecord.record_datetime >= start_of_day,
            TimeRecord.record_datetime <= end_of_day
        ).order_by(TimeRecord.record_datetime.asc()).first()

        if first_entry and first_entry.id != record.id:
            record.is_verified = True
            return

        official_datetime = datetime.combine(record_date, config.entry_1, tzinfo=tz)

        record_dt = record.record_datetime.replace(second=0, microsecond=0)
        if record_dt.tzinfo is None:
            record_dt = record_dt.replace(tzinfo=tz)

        diff_seconds = (official_datetime - record_dt).total_seconds()
        diff_minutes = diff_seconds / 60.0

        if diff_minutes <= 5:
            record.is_verified = True
        else:
            if now >= official_datetime:
                record.is_verified = True

    async def async_process_entry_record(self, db: AsyncSession, record: TimeRecord, now: datetime, tz: ZoneInfo):
        if record.user.is_tolerance_exempt:
            record.is_verified = True
            return

        record_date = record.record_datetime.date()

        target_day = DayOfWeek.from_date(record_date)
        stmt = select(UserWorkScheduleConfig).where(
            UserWorkScheduleConfig.user_id == record.user_id,
            UserWorkScheduleConfig.day_of_week == target_day.value,
            UserWorkScheduleConfig.valid_from <= record_date,
            (UserWorkScheduleConfig.valid_until.is_(None) | (UserWorkScheduleConfig.valid_until >= record_date))
        ).order_by(UserWorkScheduleConfig.valid_from.desc())
        config = await db.scalar(stmt)

        if not config or not config.entry_1:
            record.is_verified = True
            return

        start_of_day = datetime.combine(record_date, time.min, tzinfo=tz)
        end_of_day = datetime.combine(record_date, time.max, tzinfo=tz)

        first_entry_stmt = select(TimeRecord).where(
            TimeRecord.user_id == record.user_id,
            TimeRecord.record_type == RecordType.ENTRY,
            TimeRecord.deleted_at.is_(None),
            TimeRecord.record_datetime >= start_of_day,
            TimeRecord.record_datetime <= end_of_day
        ).order_by(TimeRecord.record_datetime.asc())
        first_entry = await db.scalar(first_entry_stmt)

        if first_entry and first_entry.id != record.id:
            record.is_verified = True
            return

        official_datetime = datetime.combine(record_date, config.entry_1, tzinfo=tz)

        record_dt = record.record_datetime.replace(second=0, microsecond=0)
        if record_dt.tzinfo is None:
            record_dt = record_dt.replace(tzinfo=tz)

        diff_seconds = (official_datetime - record_dt).total_seconds()
        diff_minutes = diff_seconds / 60.0

        if diff_minutes <= 5:
            record.is_verified = True
        else:
            if now >= official_datetime:
                record.is_verified = True

    def process_unverified_entries(self):
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)

        try:
            with get_db_session() as db:
                unverified_records = db.query(TimeRecord).filter(
                    TimeRecord.is_verified.is_(False),
                    TimeRecord.deleted_at.is_(None)
                ).all()

                for record in unverified_records:
                    if record.record_type == RecordType.ENTRY:
                        self._process_entry_record(db, record, now, tz)
                    elif record.record_type == RecordType.EXIT:
                        record.is_verified = True

                db.commit()
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao processar tolerancia de entradas (banco): {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao processar tolerancia de entradas: {e}")

    def reprocess_historical_entries(self, db: Session | None = None, start_date: date | None = None, end_date: date | None = None, user_ids: list[int] | None = None):
        session = db if db is not None else self.db
        assert session is not None
        assert start_date is not None
        assert end_date is not None
        assert user_ids is not None
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        entries = session.query(TimeRecord).filter(
            TimeRecord.deleted_at.is_(None),
            TimeRecord.record_datetime >= start_dt,
            TimeRecord.record_datetime <= end_dt,
            TimeRecord.user_id.in_(user_ids)
        ).all()

        for record in entries:
            if record.record_type == RecordType.ENTRY:
                self._process_entry_record(session, record, now, tz)
            elif record.record_type == RecordType.EXIT:
                record.is_verified = True

        session.commit()

    async def async_reprocess_historical_entries(self, db: AsyncSession | None = None, start_date: date | None = None,
                                                 end_date: date | None = None, user_ids: list[int] | None = None):
        session = db if db is not None else self.db
        assert session is not None
        assert start_date is not None
        assert end_date is not None
        assert user_ids is not None
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        stmt = select(TimeRecord).options(selectinload(TimeRecord.user)).where(
            TimeRecord.deleted_at.is_(None),
            TimeRecord.record_datetime >= start_dt,
            TimeRecord.record_datetime <= end_dt,
            TimeRecord.user_id.in_(user_ids)
        )
        res = await session.scalars(stmt)
        entries = list(res.all())

        for record in entries:
            if record.record_type == RecordType.ENTRY:
                await self.async_process_entry_record(session, record, now, tz)
            elif record.record_type == RecordType.EXIT:
                record.is_verified = True

        await session.commit()


tolerance_cron_service = ToleranceCronService()
