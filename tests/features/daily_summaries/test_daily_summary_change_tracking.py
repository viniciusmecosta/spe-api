from datetime import date, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.change_tracking import (
    _scope_for_adjustment,
    _scope_for_holiday,
    _scope_for_record,
    _scope_for_reopening,
    _scope_for_schedule,
    _scopes,
    enqueue_changed_days,
)
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import UserWorkScheduleConfig
from app.shared.enums import AdjustmentType, RecordType


def test_scope_for_record():
    tz = ZoneInfo(settings.TIMEZONE)
    rec = TimeRecord(
        user_id=42,
        record_datetime=datetime(2026, 6, 15, 11, 30, tzinfo=tz),
    )
    user_id, start_date, end_date = _scope_for_record(rec)
    assert user_id == 42
    assert start_date == date(2026, 6, 15)
    assert end_date == date(2026, 6, 15)


def test_scope_for_adjustment():
    adj = AdjustmentRequest(
        user_id=99,
        target_date=date(2026, 7, 20),
    )
    user_id, start_date, end_date = _scope_for_adjustment(adj)
    assert user_id == 99
    assert start_date == date(2026, 7, 20)
    assert end_date == date(2026, 7, 20)


def test_scope_for_holiday():
    hol = Holiday(date=date(2026, 12, 25))
    user_id, start_date, end_date = _scope_for_holiday(hol)
    assert user_id is None
    assert start_date == date(2026, 12, 25)
    assert end_date == date(2026, 12, 25)


def test_scope_for_reopening():
    closure = PayrollClosure(year=2026, month=4, is_closed=True)
    user_id, start_date, end_date = _scope_for_reopening(closure)
    assert user_id is None
    assert start_date == date(2026, 4, 1)
    assert end_date == date(2026, 4, 30)


def test_scope_for_schedule():
    session = MagicMock(spec=Session)
    sched = UserWorkScheduleConfig(
        user_id=10,
        day_of_week=0,
        daily_hours=8.0,
        valid_from=date(2026, 1, 15),
        valid_until=date(2026, 1, 20),
    )
    user_id, start_date, end_date = _scope_for_schedule(session, sched)
    assert user_id == 10
    assert start_date == date(2026, 1, 1)
    assert end_date == date(2026, 1, 31)


def test_scope_for_schedule_open_ended():
    session = MagicMock(spec=Session)
    session.connection.return_value.execute.return_value.scalar.return_value = date(2026, 7, 10)
    sched = UserWorkScheduleConfig(
        user_id=10,
        day_of_week=0,
        daily_hours=8.0,
        valid_from=date(2026, 7, 5),
        valid_until=None,
    )
    user_id, start_date, end_date = _scope_for_schedule(session, sched)
    assert user_id == 10
    assert start_date == date(2026, 7, 1)
    assert end_date == date(2026, 10, 31)


def test_scopes_returns_expected_scope():
    session = MagicMock(spec=Session)
    tz = ZoneInfo(settings.TIMEZONE)
    rec = TimeRecord(
        user_id=1,
        record_datetime=datetime(2026, 3, 10, 8, 0, tzinfo=tz),
    )
    result = _scopes(session, rec, None, False)
    assert result == {(1, date(2026, 3, 10), date(2026, 3, 10))}


def test_enqueue_changed_days_ignores_non_postgres():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "sqlite"
    session.info = {}
    enqueue_changed_days(session, None, None)
    assert "daily_summary_changed_days" not in session.info


def test_enqueue_changed_days_tracks_new_time_record():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.info = {}
    tz = ZoneInfo(settings.TIMEZONE)
    rec = TimeRecord(
        user_id=5,
        record_datetime=datetime(2026, 8, 14, 9, 0, tzinfo=tz),
    )
    session.new = [rec]
    session.dirty = []
    session.deleted = []

    enqueue_changed_days(session, None, None)
    assert (5, date(2026, 8, 14)) in session.info["daily_summary_changed_days"]


def test_enqueue_changed_days_tracks_schedule_changes_in_reset_excess():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.info = {}
    sched = UserWorkScheduleConfig(
        user_id=7,
        day_of_week=1,
        daily_hours=8.0,
        valid_from=date(2026, 9, 10),
        valid_until=date(2026, 9, 20),
    )
    session.new = [sched]
    session.dirty = []
    session.deleted = []

    enqueue_changed_days(session, None, None)
    assert (7, date(2026, 9, 1)) in session.info["daily_summary_changed_days"]
    assert (7, date(2026, 9, 30)) in session.info["daily_summary_changed_days"]
    assert (7, date(2026, 9, 1)) in session.info["daily_summary_reset_excess_days"]
    assert (7, date(2026, 9, 30)) in session.info["daily_summary_reset_excess_days"]


def test_enqueue_changed_days_tracks_punch_inversion():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.info = {}
    tz = ZoneInfo(settings.TIMEZONE)
    rec = TimeRecord(
        id=12,
        user_id=3,
        record_type=RecordType.EXIT,
        record_datetime=datetime(2026, 6, 2, 8, 0, tzinfo=tz),
        is_ignored=False,
    )
    session.new = []
    session.dirty = [rec]
    session.deleted = []
    session.connection.return_value.execute.return_value.mappings.return_value.first.return_value = {
        "id": 12,
        "user_id": 3,
        "record_type": RecordType.ENTRY,
        "record_datetime": datetime(2026, 6, 2, 8, 0, tzinfo=tz),
        "is_ignored": False,
        "deleted_at": None,
    }

    enqueue_changed_days(session, None, None)
    assert (3, date(2026, 6, 2)) in session.info["daily_summary_changed_days"]


def test_enqueue_changed_days_tracks_waiver_creation():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.info = {}
    adj = AdjustmentRequest(
        user_id=4,
        target_date=date(2026, 11, 15),
        adjustment_type=AdjustmentType.WAIVER,
    )
    session.new = [adj]
    session.dirty = []
    session.deleted = []

    enqueue_changed_days(session, None, None)
    assert (4, date(2026, 11, 15)) in session.info["daily_summary_changed_days"]


def test_enqueue_changed_days_skips_when_flag_present():
    session = MagicMock(spec=Session)
    session.info = {"skip_daily_summary_tracking": True}
    rec = TimeRecord(user_id=1, record_datetime=datetime(2026, 1, 1, 8, 0))
    session.new = [rec]
    session.dirty = []
    session.deleted = []

    enqueue_changed_days(session, None, None)
    assert "daily_summary_changed_days" not in session.info
