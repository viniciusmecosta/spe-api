from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_events import (
    _after_commit,
    _after_rollback,
    recalculate_changed_days,
)
from app.features.daily_summaries.daily_summary_exceptions import (
    DailySummaryUnavailableError,
)
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_schemas import (
    DaySummaryValues,
)
from app.features.daily_summaries.daily_summary_service import (
    DailySummaryService,
    daily_summary_service,
    from_legacy_period,
)
from app.features.system.system_models import AuditLog
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import UserWorkScheduleConfig
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType
from app.shared.time_calculation_service import (
    DailyTimeResult,
    PeriodTimeResult,
)


def _make_period_result(
    day: date,
    gross_seconds: float,
    accounted_seconds: float,
    expected_seconds: float,
    excess_seconds: float,
    approved_excess_seconds: float,
    missing_seconds: float,
    waiver_seconds: float,
) -> PeriodTimeResult:
    daily_res = DailyTimeResult(
        raw_worked_seconds=gross_seconds,
        waiver_seconds=waiver_seconds,
        unapproved_extra_seconds=gross_seconds - accounted_seconds,
        net_worked_seconds=accounted_seconds,
        gross_worked_seconds=gross_seconds,
        extra_seconds=max(0.0, accounted_seconds - expected_seconds),
        missing_seconds=missing_seconds,
        entries=["08:00"],
        exits=["17:00"],
        punches=["08:00 (E)", "17:00 (S)"],
        punch_blocks=["08:00 - 17:00"],
    )
    return PeriodTimeResult(
        total_net_worked_seconds=accounted_seconds,
        total_gross_worked_seconds=gross_seconds,
        total_expected_seconds=expected_seconds,
        total_waiver_seconds=waiver_seconds,
        total_unapproved_extra_seconds=gross_seconds - accounted_seconds,
        total_extra_seconds=max(0.0, accounted_seconds - expected_seconds),
        total_missing_seconds=missing_seconds,
        final_balance_seconds=accounted_seconds - expected_seconds,
        daily_results={day: daily_res},
        daily_expected_seconds={day: expected_seconds},
        daily_is_holiday={day: False},
        daily_waivers={day: None},
        total_accounted_seconds=accounted_seconds,
        total_excess_seconds=excess_seconds,
        total_approved_excess_seconds=approved_excess_seconds,
    )


def test_calculate_daily_summary_normal_day():
    day = date(2026, 5, 10)
    result = _make_period_result(
        day=day,
        gross_seconds=28800.0,
        accounted_seconds=28800.0,
        expected_seconds=28800.0,
        excess_seconds=0.0,
        approved_excess_seconds=0.0,
        missing_seconds=0.0,
        waiver_seconds=0.0,
    )
    values = from_legacy_period(day, result)
    assert values.worked_minutes == 480
    assert values.accounted_minutes == 480
    assert values.expected_minutes == 480
    assert values.excess_minutes == 0
    assert values.authorized_excess_minutes == 0
    assert values.missing_minutes == 0
    assert values.waiver_minutes == 0


def test_calculate_daily_summary_with_excess_unapproved():
    day = date(2026, 5, 10)
    result = _make_period_result(
        day=day,
        gross_seconds=32400.0,
        accounted_seconds=28800.0,
        expected_seconds=28800.0,
        excess_seconds=3600.0,
        approved_excess_seconds=0.0,
        missing_seconds=0.0,
        waiver_seconds=0.0,
    )
    values = from_legacy_period(day, result)
    assert values.worked_minutes == 540
    assert values.accounted_minutes == 480
    assert values.expected_minutes == 480
    assert values.excess_minutes == 60
    assert values.authorized_excess_minutes == 0
    assert values.missing_minutes == 0


def test_calculate_daily_summary_with_excess_approved():
    day = date(2026, 5, 10)
    result = _make_period_result(
        day=day,
        gross_seconds=32400.0,
        accounted_seconds=32400.0,
        expected_seconds=28800.0,
        excess_seconds=3600.0,
        approved_excess_seconds=3600.0,
        missing_seconds=0.0,
        waiver_seconds=0.0,
    )
    values = from_legacy_period(day, result)
    assert values.worked_minutes == 540
    assert values.accounted_minutes == 540
    assert values.expected_minutes == 480
    assert values.excess_minutes == 60
    assert values.authorized_excess_minutes == 60


def test_calculate_daily_summary_with_waiver():
    day = date(2026, 5, 10)
    result = _make_period_result(
        day=day,
        gross_seconds=28800.0,
        accounted_seconds=28800.0,
        expected_seconds=28800.0,
        excess_seconds=0.0,
        approved_excess_seconds=0.0,
        missing_seconds=0.0,
        waiver_seconds=7200.0,
    )
    values = from_legacy_period(day, result)
    assert values.worked_minutes == 480
    assert values.accounted_minutes == 480
    assert values.waiver_minutes == 120
    assert values.missing_minutes == 0


def test_calculate_daily_summary_rejects_authorized_exceeding_total():
    day = date(2026, 5, 10)
    result = _make_period_result(
        day=day,
        gross_seconds=28800.0,
        accounted_seconds=28800.0,
        expected_seconds=28800.0,
        excess_seconds=1800.0,
        approved_excess_seconds=3600.0,
        missing_seconds=0.0,
        waiver_seconds=0.0,
    )
    with pytest.raises(ValueError, match="Authorized excess exceeds total excess"):
        from_legacy_period(day, result)


def test_calculate_daily_summary_rejects_accounted_exceeding_worked():
    day = date(2026, 5, 10)
    result = _make_period_result(
        day=day,
        gross_seconds=20000.0,
        accounted_seconds=28800.0,
        expected_seconds=28800.0,
        excess_seconds=0.0,
        approved_excess_seconds=0.0,
        missing_seconds=0.0,
        waiver_seconds=0.0,
    )
    with pytest.raises(ValueError, match="Accounted time exceeds worked time"):
        from_legacy_period(day, result)


def test_calculate_daily_summary_rejects_negative_values():
    day = date(2026, 5, 10)
    result = _make_period_result(
        day, -60, 0, 0, 0, 0, 0, 0
    )

    with pytest.raises(ValueError, match="Negative apuration value"):
        from_legacy_period(day, result)


def test_dispatch_after_commit_and_rollback():
    session = MagicMock(spec=Session)
    session.info = {
        "daily_summary_changed_days": {(1, date(2026, 5, 1)), (2, date(2026, 5, 2))},
        "daily_summary_reset_excess_days": {(1, date(2026, 5, 1))},
    }

    with patch("app.features.daily_summaries.daily_summary_events.schedule_days") as mock_schedule:
        _after_commit(session)
        mock_schedule.assert_called_once_with(
            {(1, date(2026, 5, 1)), (2, date(2026, 5, 2))},
            {(1, date(2026, 5, 1))},
        )
        assert "daily_summary_changed_days" not in session.info
        assert "daily_summary_reset_excess_days" not in session.info

    session.info = {
        "daily_summary_changed_days": {(1, date(2026, 5, 1))},
        "daily_summary_reset_excess_days": {(1, date(2026, 5, 1))},
    }
    _after_rollback(session)
    assert "daily_summary_changed_days" not in session.info
    assert "daily_summary_reset_excess_days" not in session.info


@pytest.mark.asyncio
async def test_recalculate_changed_days_calls_service():
    with patch(
        "app.features.daily_summaries.daily_summary_service.daily_summary_service.recalculate_day",
        new_callable=AsyncMock,
    ) as mock_recalc:
        days = {(1, date(2026, 5, 1)), (2, date(2026, 5, 2))}
        await recalculate_changed_days(days)
        assert mock_recalc.await_count == 2
        mock_recalc.assert_any_await(1, date(2026, 5, 1), reset_excess=False)
        mock_recalc.assert_any_await(2, date(2026, 5, 2), reset_excess=False)


@pytest.mark.asyncio
async def test_recalculate_changed_days_with_reset_excess_flag():
    with patch(
        "app.features.daily_summaries.daily_summary_service.daily_summary_service.recalculate_day",
        new_callable=AsyncMock,
    ) as mock_recalc:
        days = {(1, date(2026, 5, 1)), (2, date(2026, 5, 2))}
        reset_days = {(1, date(2026, 5, 1))}
        await recalculate_changed_days(days, reset_excess_days=reset_days)
        assert mock_recalc.await_count == 2
        mock_recalc.assert_any_await(1, date(2026, 5, 1), reset_excess=True)
        mock_recalc.assert_any_await(2, date(2026, 5, 2), reset_excess=False)


@pytest.mark.asyncio
async def test_read_service_raises_when_summary_missing():
    service = DailySummaryService()
    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    session.scalars = AsyncMock(return_value=scalars_mock)
    session.sync_session = MagicMock()
    with pytest.raises(DailySummaryUnavailableError):
        await service.build_period(
            session=session,
            user_id=1,
            first=date(2026, 1, 1),
            last=date(2026, 1, 2),
            records=[
                TimeRecord(
                    user_id=1,
                    record_type=RecordType.ENTRY,
                    record_datetime=datetime(2026, 1, 1, 8, 0),
                )
            ],
            adjustments=[],
            holidays=[],
            historical_schedules=[],
        )


@pytest.mark.asyncio
async def test_build_period_treats_missing_inactive_days_as_zero_without_inserting_rows():
    first = date(2026, 5, 11)
    last = date(2026, 5, 12)
    schedule = UserWorkScheduleConfig(
        day_of_week=first.weekday(),
        daily_hours=8,
        valid_from=date(2026, 1, 1),
        valid_until=None,
    )
    service = DailySummaryService()
    with patch.object(
        service, "_load_period_rows", new=AsyncMock(return_value={})
    ):
        result = await service.build_period(
            MagicMock(), 1, first, last, [], [], [], [schedule]
        )

    assert result.total_gross_worked_seconds == 0
    assert result.total_accounted_seconds == 0
    assert result.total_expected_seconds == 8 * 3600
    assert result.total_missing_seconds == 8 * 3600
    assert result.daily_expected_seconds[last] == 0


@pytest.mark.asyncio
async def test_build_period_without_schedule_preserves_legacy_balance():
    day = date(2026, 5, 10)
    summary = DailySummary(
        user_id=1,
        apuration_date=day,
        worked_minutes=480,
        accounted_minutes=480,
        expected_minutes=0,
        excess_minutes=0,
        authorized_excess_minutes=0,
        missing_minutes=0,
        waiver_minutes=0,
    )
    service = DailySummaryService()
    with patch.object(
        service, "_load_period_rows", new=AsyncMock(return_value={day: summary})
    ):
        result = await service.build_period(
            session=MagicMock(),
            user_id=1,
            first=day,
            last=day,
            records=[],
            adjustments=[],
            holidays=[],
            historical_schedules=[],
        )
    assert result.final_balance_seconds == 0
    assert result.daily_accounted_results[day].accounted_seconds == 28800


@pytest.mark.asyncio
async def test_build_period_reads_saved_minutes_without_recalculating_records():
    day = date(2026, 5, 11)
    summary = DailySummary(
        user_id=1,
        apuration_date=day,
        worked_minutes=540,
        accounted_minutes=480,
        expected_minutes=480,
        excess_minutes=60,
        authorized_excess_minutes=0,
        missing_minutes=0,
        waiver_minutes=0,
    )
    records = [
        TimeRecord(user_id=1, record_type=RecordType.ENTRY,
                   record_datetime=datetime(2026, 5, 11, 8, 0)),
        TimeRecord(user_id=1, record_type=RecordType.EXIT,
                   record_datetime=datetime(2026, 5, 11, 18, 0)),
    ]
    adjustment = AdjustmentRequest(
        user_id=1,
        target_date=day,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.PENDING,
        amount_hours=1,
    )
    service = DailySummaryService()
    with patch.object(
        service, "_load_period_rows", new=AsyncMock(return_value={day: summary})
    ), patch(
        "app.features.daily_summaries.daily_summary_service.time_calculation_service.calculate_period_time",
        side_effect=AssertionError("read recalculated period"),
    ), patch(
        "app.features.daily_summaries.daily_summary_service.time_calculation_service._process_records",
        side_effect=AssertionError("read recalculated punches"),
    ):
        result = await service.build_period(
            MagicMock(), 1, day, day, records, [adjustment], [], []
        )
    assert result.total_accounted_seconds == 480 * 60
    assert result.total_unapproved_extra_seconds == 60 * 60
    assert result.daily_results[day].punch_blocks == ["08:00 - 18:00"]


@pytest.mark.asyncio
async def test_load_period_rows_supports_sync_session():
    day = date(2026, 5, 11)
    row = DailySummary(user_id=1, apuration_date=day)
    scalar_result = MagicMock()
    scalar_result.all.return_value = [row]
    session = MagicMock(spec=Session)
    session.scalars.return_value = scalar_result

    result = await DailySummaryService()._load_period_rows(session, 1, day, day)

    assert result == {day: row}


@pytest.mark.asyncio
async def test_calculate_user_day_returns_when_user_is_missing():
    session = AsyncMock()
    session.scalar.return_value = None

    await DailySummaryService()._calculate_user_day(
        session, 1, date(2026, 5, 11), refresh_excess=False
    )

    session.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_recalculate_day_dispatches_with_refresh_enabled(mocker):
    service = DailySummaryService()
    calculate = mocker.patch.object(service, "calculate_day", new_callable=AsyncMock)
    target = date(2026, 5, 11)

    await service.recalculate_day(1, target, reset_excess=True)

    calculate.assert_awaited_once_with(
        1, target, refresh_excess=True, allow_closed=False, reset_excess=True
    )


def _scalar_result(items):
    result = MagicMock()
    result.all.return_value = items
    return result


@pytest.mark.asyncio
async def test_calculate_user_day_invalidates_changed_reviewed_excess(mocker):
    day = date(2026, 5, 11)
    service = DailySummaryService()
    reviewed = AdjustmentRequest(
        id=45,
        user_id=1,
        target_date=day,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.APPROVED,
        amount_hours=1,
        approved_amount_hours=0.5,
    )
    period = _make_period_result(day, 36000, 28800, 28800, 7200, 0, 0, 0)
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.return_value = MagicMock(historical_schedules=[])
    session.scalars.side_effect = [
        _scalar_result([]),
        _scalar_result([reviewed]),
        _scalar_result([]),
        _scalar_result([]),
    ]
    calculate = mocker.patch(
        "app.features.daily_summaries.daily_summary_service.time_calculation_service.calculate_period_time",
        side_effect=[period, period],
    )
    evaluate = mocker.patch(
        "app.features.daily_summaries.daily_summary_service.daily_excess_service.evaluate_user_day_async",
        new_callable=AsyncMock,
    )
    upsert = mocker.patch(
        "app.features.daily_summaries.daily_summary_service.daily_summary_repository.upsert",
        new_callable=AsyncMock,
    )

    await service._calculate_user_day(session, 1, day, refresh_excess=True)

    assert reviewed.deleted_at is not None
    assert session.add.call_args.args[0].action == "INVALIDATE_DAILY_EXCESS"
    evaluate.assert_awaited_once_with(session, 1, day)
    assert calculate.call_count == 2
    upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_calculate_user_day_keeps_current_reviewed_excess(mocker):
    day = date(2026, 5, 11)
    service = DailySummaryService()
    reviewed = AdjustmentRequest(
        id=46,
        user_id=1,
        target_date=day,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.APPROVED,
        amount_hours=2,
    )
    period = _make_period_result(day, 36000, 28800, 28800, 7200, 0, 0, 0)
    session = AsyncMock()
    session.scalar.return_value = MagicMock(historical_schedules=[])
    session.scalars.side_effect = [
        _scalar_result([]),
        _scalar_result([reviewed]),
        _scalar_result([]),
    ]
    mocker.patch(
        "app.features.daily_summaries.daily_summary_service.time_calculation_service.calculate_period_time",
        return_value=period,
    )
    evaluate = mocker.patch(
        "app.features.daily_summaries.daily_summary_service.daily_excess_service.evaluate_user_day_async",
        new_callable=AsyncMock,
    )
    upsert = mocker.patch(
        "app.features.daily_summaries.daily_summary_service.daily_summary_repository.upsert",
        new_callable=AsyncMock,
    )

    await service._calculate_user_day(session, 1, day, refresh_excess=True)

    assert reviewed.deleted_at is None
    evaluate.assert_not_awaited()
    upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_calculate_user_day_resets_reviewed_excess_before_calculating(mocker):
    day = date(2026, 5, 11)
    service = DailySummaryService()
    reviewed = AdjustmentRequest(
        id=47,
        user_id=1,
        target_date=day,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.REJECTED,
        amount_hours=1,
    )
    pending = AdjustmentRequest(
        id=48,
        user_id=1,
        target_date=day,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.PENDING,
        amount_hours=1,
    )
    period = _make_period_result(day, 28800, 28800, 28800, 0, 0, 0, 0)
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.return_value = MagicMock(historical_schedules=[])
    session.scalars.side_effect = [
        _scalar_result([reviewed, pending]),
        _scalar_result([]),
        _scalar_result([]),
        _scalar_result([]),
    ]
    mocker.patch(
        "app.features.daily_summaries.daily_summary_service.time_calculation_service.calculate_period_time",
        return_value=period,
    )
    evaluate = mocker.patch(
        "app.features.daily_summaries.daily_summary_service.daily_excess_service.evaluate_user_day_async",
        new_callable=AsyncMock,
    )
    upsert = mocker.patch(
        "app.features.daily_summaries.daily_summary_service.daily_summary_repository.upsert",
        new_callable=AsyncMock,
    )

    await service._calculate_user_day(session, 1, day, refresh_excess=False, reset_excess=True)

    assert reviewed.deleted_at is not None
    assert pending.deleted_at is not None
    assert session.add.call_count == 1
    evaluate.assert_awaited_once_with(session, 1, day, overwrite_reviewed=True)
    upsert.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "closed_id", "allow_closed", "expected_scalar_calls", "should_calculate"),
    [
        (None, None, False, 1, False),
        (1, 33, False, 2, False),
        (1, None, False, 3, True),
        (1, None, True, 2, True),
    ],
)
async def test_calculate_day_checks_user_and_closure_before_upsert(
    mocker, user_id, closed_id, allow_closed, expected_scalar_calls, should_calculate
):
    service = DailySummaryService()
    day = date(2026, 5, 11)
    session = AsyncMock()
    session.sync_session = MagicMock(info={})
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=transaction)
    session.scalar.side_effect = (
        [user_id]
        + ([closed_id] if user_id is not None and not allow_closed else [])
        + ([49] if should_calculate else [])
    )
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    calculated = mocker.patch.object(service, "_calculate_user_day", new_callable=AsyncMock)
    mocker.patch(
        "app.features.daily_summaries.daily_summary_service.AsyncSessionLocal",
        return_value=manager,
    )

    await service.calculate_day(
        1, day, refresh_excess=True, allow_closed=allow_closed
    )

    assert session.scalar.await_count == expected_scalar_calls
    assert session.execute.await_count == int(should_calculate)
    assert calculated.await_count == int(should_calculate)


@pytest.mark.asyncio
async def test_calculate_user_day_with_reset_excess():
    from app.features.daily_summaries.daily_summary_service import (
        daily_summary_service,
    )
    from app.features.users.user_models import User

    session = AsyncMock()
    session.add = MagicMock()
    user = User(id=1, name="Tester")
    user.historical_schedules = []
    session.scalar.return_value = user
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    session.scalars.return_value = scalars_mock

    with patch(
        "app.features.daily_summaries.daily_summary_service.daily_excess_service.evaluate_user_day_async",
        new_callable=AsyncMock,
    ) as mock_excess, patch(
        "app.features.daily_summaries.daily_summary_service.daily_summary_repository.upsert",
        new_callable=AsyncMock,
    ) as mock_upsert:
        await daily_summary_service._calculate_user_day(
            session, user_id=1, day=date(2026, 5, 10), refresh_excess=True, reset_excess=True
        )
        mock_excess.assert_awaited_once_with(
            session, 1, date(2026, 5, 10), overwrite_reviewed=True
        )
        assert mock_upsert.await_count == 1


@pytest.mark.asyncio
async def test_schedule_change_preserves_reviewed_excess_in_history():
    from app.features.users.user_models import User

    day = date(2026, 5, 10)
    reviewed = AdjustmentRequest(
        id=42,
        user_id=1,
        target_date=day,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.APPROVED,
        amount_hours=1.0,
        approved_amount_hours=1.0,
    )
    session = AsyncMock()
    session.add = MagicMock()
    user = User(id=1, name="Tester")
    user.historical_schedules = []
    session.scalar.return_value = user
    previous = MagicMock()
    previous.all.return_value = [reviewed]
    empty = MagicMock()
    empty.all.return_value = []
    session.scalars.side_effect = [previous, empty, empty, empty]

    with patch(
        "app.features.daily_summaries.daily_summary_service.daily_excess_service.evaluate_user_day_async",
        new_callable=AsyncMock,
    ), patch(
        "app.features.daily_summaries.daily_summary_service.daily_summary_repository.upsert",
        new_callable=AsyncMock,
    ):
        await daily_summary_service._calculate_user_day(
            session, user_id=1, day=day, refresh_excess=True, reset_excess=True
        )

    assert reviewed.deleted_at is not None
    audit = next(
        call.args[0] for call in session.add.call_args_list
        if isinstance(call.args[0], AuditLog)
    )
    assert audit.entity_id == 42
    assert audit.old_data["status"] == AdjustmentStatus.APPROVED.value
    assert audit.new_data["reason"] == "SCHEDULE_CHANGED"

