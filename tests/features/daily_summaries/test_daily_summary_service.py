from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.features.daily_summaries.calculator import (
    DaySummaryValues,
    from_legacy_period,
)
from app.features.daily_summaries.dispatch import (
    _after_commit,
    _after_rollback,
    recalculate_changed_days,
)
from app.features.daily_summaries.read_service import (
    DailySummaryReadService,
    DailySummaryUnavailableError,
)
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


def test_dispatch_after_commit_and_rollback():
    session = MagicMock(spec=Session)
    session.info = {"daily_summary_changed_days": {(1, date(2026, 5, 1)), (2, date(2026, 5, 2))}}

    with patch("app.features.daily_summaries.dispatch.schedule_days") as mock_schedule:
        _after_commit(session)
        mock_schedule.assert_called_once_with({(1, date(2026, 5, 1)), (2, date(2026, 5, 2))})
        assert "daily_summary_changed_days" not in session.info

    session.info = {"daily_summary_changed_days": {(1, date(2026, 5, 1))}}
    _after_rollback(session)
    assert "daily_summary_changed_days" not in session.info


@pytest.mark.asyncio
async def test_recalculate_changed_days_calls_service():
    with patch(
        "app.features.daily_summaries.recalculation_service.daily_summary_recalculation_service.recalculate_day",
        new_callable=AsyncMock,
    ) as mock_recalc:
        days = {(1, date(2026, 5, 1)), (2, date(2026, 5, 2))}
        await recalculate_changed_days(days)
        assert mock_recalc.await_count == 2
        mock_recalc.assert_any_await(1, date(2026, 5, 1))
        mock_recalc.assert_any_await(2, date(2026, 5, 2))


@pytest.mark.asyncio
async def test_read_service_raises_when_summary_missing():
    service = DailySummaryReadService()
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
            records=[],
            adjustments=[],
            holidays=[],
            historical_schedules=[],
        )
