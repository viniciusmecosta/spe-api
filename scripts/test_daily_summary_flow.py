import importlib
import asyncio
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.config import settings
from app.database.session import AsyncSessionLocal, SessionLocal
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_service import (
    daily_summary_service,
)
from app.features.daily_summaries.daily_summary_events import _scopes
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared.enums import AdjustmentType, RecordType


def _queued(session, user_id: int, day: date) -> bool:
    return (user_id, day) in session.info.get("daily_summary_changed_days", set())


def test_time_record_change_tracks_both_its_previous_and_current_days():
    session = SimpleNamespace()
    local_timezone = ZoneInfo(settings.TIMEZONE)
    previous_day, current_day = date(2026, 10, 1), date(2026, 10, 2)
    previous = datetime.combine(previous_day, time(12), tzinfo=local_timezone)
    current = datetime.combine(current_day, time(12), tzinfo=local_timezone)
    record = TimeRecord(
        user_id=7, record_type=RecordType.ENTRY, record_datetime=current,
    )
    scopes = _scopes(session, record, {"user_id": 7, "record_datetime": previous}, False)
    assert scopes == {
        (7, previous_day, previous_day),
        (7, current_day, current_day),
    }


def test_deleted_time_record_tracks_only_the_persisted_day():
    session = SimpleNamespace()
    persisted = datetime(2026, 10, 3, 8, tzinfo=timezone.utc)
    record = TimeRecord(
        user_id=7, record_type=RecordType.ENTRY,
        record_datetime=datetime(2026, 10, 4, 8, tzinfo=timezone.utc),
    )
    scopes = _scopes(session, record, {"user_id": 7, "record_datetime": persisted}, True)
    assert scopes == {(7, date(2026, 10, 3), date(2026, 10, 3))}


async def _test_calculation_rollback() -> None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(TimeRecord.user_id, TimeRecord.record_datetime)
            .where(TimeRecord.record_datetime >= datetime(2026, 10, 1, tzinfo=timezone.utc))
            .order_by(TimeRecord.record_datetime)
            .limit(1)
        )).first()
        assert row is not None
        user_id, timestamp = row
        await daily_summary_service._calculate_user_day(
            session, user_id, timestamp.date(), refresh_excess=True
        )
        await session.flush()
        await session.rollback()


def main() -> None:
    importlib.import_module("app.features.companies.company_models")
    importlib.import_module("app.features.printers.printer_models")
    importlib.import_module("app.features.devices.device_models")
    with SessionLocal() as session:
        user_id = session.scalar(select(User.id).order_by(User.id).limit(1))
        assert user_id is not None
        source_count = session.scalar(select(func.count()).select_from(TimeRecord))
        summary_count = session.scalar(select(func.count()).select_from(DailySummary))
        first = date(2099, 1, 5)
        session.add(TimeRecord(
            user_id=user_id, record_type=RecordType.ENTRY,
            record_datetime=datetime(2099, 1, 5, 8, tzinfo=timezone.utc),
        ))
        session.flush()
        assert _queued(session, user_id, first)

        session.add(AdjustmentRequest(
            user_id=user_id, target_date=first + timedelta(days=1),
            adjustment_type=AdjustmentType.WAIVER,
        ))
        session.flush()
        assert _queued(session, user_id, first + timedelta(days=1))

        session.add(Holiday(date=first + timedelta(days=2), name="Teste transacional"))
        session.flush()
        assert _queued(session, user_id, first + timedelta(days=2))

        session.add(UserWorkScheduleConfig(
            user_id=user_id, day_of_week=(first + timedelta(days=3)).weekday(), daily_hours=8,
            valid_from=first + timedelta(days=3),
            valid_until=first + timedelta(days=4),
        ))
        session.flush()
        assert _queued(session, user_id, first + timedelta(days=3))
        assert not _queued(session, user_id, first + timedelta(days=4))

        local_today = datetime.now(ZoneInfo(settings.TIMEZONE)).date()
        open_start = local_today - timedelta(days=14)
        session.add(UserWorkScheduleConfig(
            user_id=user_id, day_of_week=open_start.weekday(), daily_hours=8,
            valid_from=open_start, valid_until=None,
        ))
        session.flush()
        assert _queued(session, user_id, open_start)
        assert not _queued(session, user_id, local_today + timedelta(days=7))

        closure = session.scalar(select(PayrollClosure).where(
            PayrollClosure.is_closed.is_(True),
            PayrollClosure.deleted_at.is_(None),
        ).limit(1))
        if closure is not None:
            closure.deleted_at = datetime.now(timezone.utc)
            session.flush()
            assert _queued(session, user_id, date(closure.year, closure.month, 1))

        existing_record = session.scalar(
            select(TimeRecord).order_by(TimeRecord.id).limit(1)
        )
        if existing_record is not None:
            existing_day = existing_record.record_datetime.date()
            before_metadata_change = _queued(session, existing_record.user_id, existing_day)
            existing_record.device_name = "Teste transacional"
            session.flush()
            assert _queued(session, existing_record.user_id, existing_day) == before_metadata_change

        session.rollback()
        assert session.scalar(select(func.count()).select_from(TimeRecord)) == source_count
        assert session.scalar(select(func.count()).select_from(DailySummary)) == summary_count
        assert not _queued(session, user_id, first)
        session.rollback()
    asyncio.run(_test_calculation_rollback())
    print("OK: app changes schedule affected days and rollback leaves no data behind")


if __name__ == "__main__":
    main()
