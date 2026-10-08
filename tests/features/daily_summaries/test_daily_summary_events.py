from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_events import (
    _after_commit,
    _after_rollback,
    _local_day,
    _old_row,
    _scope_for_adjustment,
    _scope_for_holiday,
    _scope_for_record,
    _scope_for_reopening,
    _scope_for_schedule,
    _scopes,
    enqueue_changed_days,
    recalculate_changed_days,
    schedule_days,
)
from app.features.daily_summaries import daily_summary_events
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


def test_local_day_supports_naive_and_aware_datetimes():
    naive = datetime(2026, 6, 15, 23, 30)
    aware = datetime(2026, 6, 15, 23, 30, tzinfo=ZoneInfo("UTC"))

    assert _local_day(naive) == date(2026, 6, 15)
    assert _local_day(aware) == aware.astimezone(ZoneInfo(settings.TIMEZONE)).date()


def test_old_row_returns_none_without_id_and_loaded_mapping_with_id():
    session = MagicMock(spec=Session)
    assert _old_row(session, TimeRecord(user_id=4)) is None

    session.connection.return_value.execute.return_value.mappings.return_value.first.return_value = {
        "id": 11,
        "user_id": 4,
    }
    assert _old_row(session, TimeRecord(id=11, user_id=4)) == {"id": 11, "user_id": 4}


def test_scope_for_adjustment():
    adj = AdjustmentRequest(
        user_id=99,
        target_date=date(2026, 7, 20),
    )
    user_id, start_date, end_date = _scope_for_adjustment(adj)
    assert user_id == 99
    assert start_date == date(2026, 7, 20)
    assert end_date == date(2026, 7, 20)

    assert _scope_for_adjustment({"user_id": 9, "target_date": date(2026, 7, 21)}) == (
        9, date(2026, 7, 21), date(2026, 7, 21)
    )


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
    assert start_date == date(2026, 1, 15)
    assert end_date == date(2026, 1, 20)


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
    assert start_date == date(2026, 7, 5)
    assert end_date == max(
        date(2026, 7, 5), date(2026, 7, 10),
        datetime.now(ZoneInfo(settings.TIMEZONE)).date(),
    )


def test_schedule_edit_recalculates_only_old_and_new_weekdays():
    session = MagicMock(spec=Session)
    new = UserWorkScheduleConfig(
        user_id=7,
        day_of_week=2,
        daily_hours=8.0,
        valid_from=date(2026, 9, 10),
        valid_until=date(2026, 9, 20),
    )
    old = {
        "user_id": 7,
        "day_of_week": 1,
        "valid_from": date(2026, 9, 10),
        "valid_until": date(2026, 9, 20),
    }
    assert _scopes(session, new, old, False) == {
        (7, date(2026, 9, 15), date(2026, 9, 15)),
        (7, date(2026, 9, 16), date(2026, 9, 16)),
    }


def test_scopes_returns_expected_scope():
    session = MagicMock(spec=Session)
    tz = ZoneInfo(settings.TIMEZONE)
    rec = TimeRecord(
        user_id=1,
        record_datetime=datetime(2026, 3, 10, 8, 0, tzinfo=tz),
    )
    result = _scopes(session, rec, None, False)
    assert result == {(1, date(2026, 3, 10), date(2026, 3, 10))}


def test_scope_for_closed_payroll_reopen_and_non_reopen():
    session = MagicMock(spec=Session)
    closure = PayrollClosure(year=2026, month=12, is_closed=False)
    old = {"year": 2026, "month": 12, "is_closed": True}

    assert _scopes(session, closure, old, False) == {
        (None, date(2026, 12, 1), date(2026, 12, 31))
    }
    assert _scopes(session, closure, {**old, "is_closed": False}, False) == set()


def test_scopes_support_schedule_deletion_and_unknown_sources():
    session = MagicMock(spec=Session)
    schedule = UserWorkScheduleConfig(
        user_id=7,
        day_of_week=0,
        daily_hours=8,
        valid_from=date(2026, 9, 1),
        valid_until=date(2026, 9, 10),
    )
    old = {
        "user_id": 7,
        "day_of_week": 1,
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 10),
    }

    assert _scopes(session, schedule, old, True) == {
        (7, date(2026, 9, 1), date(2026, 9, 1)),
        (7, date(2026, 9, 8), date(2026, 9, 8)),
    }
    assert _scopes(session, object(), None, False) == set()


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
    assert session.info["daily_summary_changed_days"] == {(7, date(2026, 9, 15))}
    assert session.info["daily_summary_reset_excess_days"] == {(7, date(2026, 9, 15))}


def test_enqueue_changed_days_tracks_dirty_schedule_changes():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.info = {}
    schedule = UserWorkScheduleConfig(
        id=18,
        user_id=7,
        day_of_week=1,
        daily_hours=8.0,
        valid_from=date(2026, 9, 10),
        valid_until=date(2026, 9, 20),
    )
    schedule.day_of_week = 2
    session.new = []
    session.dirty = [schedule]
    session.deleted = []
    session.connection.return_value.execute.return_value.mappings.return_value.first.return_value = {
        "id": 18,
        "user_id": 7,
        "day_of_week": 1,
        "valid_from": date(2026, 9, 10),
        "valid_until": date(2026, 9, 20),
    }

    enqueue_changed_days(session, None, None)

    assert session.info["daily_summary_changed_days"] == {
        (7, date(2026, 9, 15)),
        (7, date(2026, 9, 16)),
    }
    assert session.info["daily_summary_reset_excess_days"] == session.info[
        "daily_summary_changed_days"
    ]


def test_enqueue_changed_days_tracks_deleted_schedule():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.info = {}
    schedule = UserWorkScheduleConfig(id=18, user_id=7)
    session.new = []
    session.dirty = []
    session.deleted = [schedule]
    session.connection.return_value.execute.return_value.mappings.return_value.first.return_value = {
        "id": 18,
        "user_id": 7,
        "day_of_week": 1,
        "valid_from": date(2026, 9, 10),
        "valid_until": date(2026, 9, 20),
    }

    enqueue_changed_days(session, None, None)

    assert session.info["daily_summary_changed_days"] == {
        (7, date(2026, 9, 15)),
    }
    assert session.info["daily_summary_reset_excess_days"] == session.info[
        "daily_summary_changed_days"
    ]


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


def test_enqueue_changed_days_returns_without_changes():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.info = {}
    session.new = []
    session.dirty = []
    session.deleted = []

    enqueue_changed_days(session, None, None)

    assert session.info == {}


def test_enqueue_changed_days_expands_holiday_change_to_all_users():
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    session.connection.return_value.execute.return_value.scalars.return_value.all.return_value = [2, 5]
    session.info = {}
    session.new = [Holiday(date=date(2026, 12, 25))]
    session.dirty = []
    session.deleted = []

    enqueue_changed_days(session, None, None)

    assert session.info["daily_summary_changed_days"] == {
        (2, date(2026, 12, 25)),
        (5, date(2026, 12, 25)),
    }


def test_after_commit_waits_for_recalculation_and_rollback_clears_state():
    task = MagicMock()
    task_result = MagicMock()
    session = MagicMock(spec=Session)
    session.info = {
        "daily_summary_changed_days": {(1, date(2026, 4, 1))},
        "daily_summary_reset_excess_days": {(1, date(2026, 4, 1))},
        "await_daily_summary": True,
    }
    with patch("app.features.daily_summaries.daily_summary_events.schedule_days", return_value=task) as schedule:
        _after_commit(session)

    schedule.assert_called_once_with(
        {(1, date(2026, 4, 1))}, {(1, date(2026, 4, 1))}
    )
    assert session.info["daily_summary_pending_tasks"] == [task]
    assert "daily_summary_changed_days" not in session.info

    session.info["daily_summary_changed_days"] = set()
    session.info["daily_summary_reset_excess_days"] = set()
    _after_rollback(session)
    assert "daily_summary_changed_days" not in session.info
    assert "daily_summary_reset_excess_days" not in session.info


def test_schedule_days_returns_none_for_empty_days():
    assert schedule_days(set()) is None


def test_schedule_days_creates_task_inside_running_loop():
    async def run():
        with patch(
            "app.features.daily_summaries.daily_summary_events.recalculate_changed_days",
            new_callable=AsyncMock,
            return_value=True,
        ):
            task = schedule_days({(1, date(2026, 4, 1))})
            assert await task is True

    import asyncio

    asyncio.run(run())


def test_schedule_days_uses_bound_loop_without_running_loop():
    loop = MagicMock()
    loop.is_running.return_value = True
    coro_args = []

    def dispatch(coro, target_loop):
        coro_args.append((coro, target_loop))

    with patch.object(daily_summary_events, "_dispatch_loop", loop), patch(
        "app.features.daily_summaries.daily_summary_events.asyncio.get_running_loop",
        side_effect=RuntimeError,
    ), patch(
        "app.features.daily_summaries.daily_summary_events.asyncio.run_coroutine_threadsafe",
        side_effect=dispatch,
    ):
        assert schedule_days({(1, date(2026, 4, 1))}) is None

    assert coro_args[0][1] is loop
    coro_args[0][0].close()


def test_schedule_days_uses_executor_without_bound_loop():
    submitted = []

    def submit(function, coro):
        submitted.append((function, coro))

    with patch.object(daily_summary_events, "_dispatch_loop", None), patch(
        "app.features.daily_summaries.daily_summary_events.asyncio.get_running_loop",
        side_effect=RuntimeError,
    ), patch.object(daily_summary_events._sync_executor, "submit", side_effect=submit):
        assert schedule_days({(1, date(2026, 4, 1))}) is None

    assert submitted[0][0] is daily_summary_events.asyncio.run
    submitted[0][1].close()


@pytest.mark.asyncio
async def test_recalculate_changed_days_retries_and_returns_failure_after_three_errors(mocker):
    from app.features.daily_summaries.daily_summary_service import daily_summary_service

    recalculate = mocker.patch.object(
        daily_summary_service,
        "recalculate_day",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("retry"), True],
    )
    sleep = mocker.patch(
        "app.features.daily_summaries.daily_summary_events.asyncio.sleep",
        new_callable=AsyncMock,
    )

    assert await recalculate_changed_days({(1, date(2026, 4, 1))}) is True
    assert recalculate.await_count == 2
    sleep.assert_awaited_once_with(1)

    recalculate.reset_mock(side_effect=True)
    recalculate.side_effect = RuntimeError("failure")
    assert await recalculate_changed_days({(1, date(2026, 4, 1))}) is False
    assert recalculate.await_count == 3
    assert sleep.await_count == 3
