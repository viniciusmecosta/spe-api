from datetime import date, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.daily_summaries.daily_summary_service import daily_summary_service
from app.shared.time_calculation_service import time_calculation_service
from app.shared.work_schedule_time import minutes_to_seconds


@pytest.mark.parametrize(('clocks', 'legacy_hours', 'expected_seconds'), [
    (('08:00', '12:00', '13:00', '17:01'), 8.02, 28860),
    (('22:00', '02:00', None, None), 4, 14400),
    ((None, None, '22:15', '02:45'), 4.5, 16200),
    (('08:00', '12:00', '13:00', None), 8.01, 28860),
    ((None, None, None, None), 8.01, 28860),
    (('08:00:59', '16:01:01', None, None), 8.02, 28860),
    (('22:00:59', '02:01:01', None, None), 4.02, 14460),
])
def test_expected_time_uses_complete_intervals_or_legacy_value(clocks, legacy_hours, expected_seconds):
    day = date(2026, 9, 29)
    entry_1, exit_1, entry_2, exit_2 = [time.fromisoformat(clock) if clock else None for clock in clocks]
    schedule = SimpleNamespace(day_of_week=day.weekday(), valid_from=day, valid_until=day,
                               daily_minutes=int(Decimal(str(legacy_hours)) * 60 + Decimal("0.5")), entry_1=entry_1, exit_1=exit_1,
                               entry_2=entry_2, exit_2=exit_2, is_daily_excess_enabled=True)
    result = time_calculation_service.calculate_period_time(day, day, [], [], [], [schedule])
    assert result.daily_expected_seconds[day] == pytest.approx(expected_seconds)
    assert result.total_missing_seconds == pytest.approx(expected_seconds)


def test_period_totals_sum_each_daily_minute_for_legacy_schedule():
    start = date(2026, 9, 15)
    end = date(2026, 9, 29)
    schedule = SimpleNamespace(day_of_week=start.weekday(), valid_from=start, valid_until=end,
                               daily_minutes=481, entry_1=None, exit_1=None, entry_2=None, exit_2=None,
                               is_daily_excess_enabled=True)
    result = time_calculation_service.calculate_period_time(start, end, [], [], [], [schedule])
    assert result.total_expected_seconds == 3 * 481 * 60
    assert result.total_missing_seconds == 3 * 481 * 60


@pytest.mark.asyncio
async def test_saved_summary_totals_sum_daily_displayed_minutes(monkeypatch):
    start = date(2026, 9, 15)
    rows = {start + timedelta(days=offset): SimpleNamespace(
        expected_minutes=480.6, worked_minutes=480.6, accounted_minutes=480.6,
        waiver_minutes=0, missing_minutes=0, excess_minutes=0, authorized_excess_minutes=0,
    ) for offset in range(3)}
    monkeypatch.setattr(daily_summary_service, '_load_period_rows', AsyncMock(return_value=rows))
    result = await daily_summary_service.build_period(None, 1, start, start + timedelta(days=2), [], [], [], [])
    assert result.total_expected_seconds == 3 * 481 * 60
    assert result.total_gross_worked_seconds == 3 * 481 * 60
    assert result.total_accounted_seconds == 3 * 481 * 60


@pytest.mark.parametrize(('minutes', 'expected'), [(480.49, 480), (480.5, 481), (480.51, 481), (502.5, 503)])
def test_legacy_fraction_uses_existing_minute_rounding(minutes, expected):
    assert minutes_to_seconds(minutes) == expected * 60
