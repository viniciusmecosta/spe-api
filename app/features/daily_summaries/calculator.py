from dataclasses import dataclass
from datetime import date

from app.shared.time_calculation_service import PeriodTimeResult


@dataclass(frozen=True)
class DaySummaryValues:
    worked_minutes: int
    accounted_minutes: int
    expected_minutes: int
    excess_minutes: int
    authorized_excess_minutes: int
    missing_minutes: int
    waiver_minutes: int


def from_legacy_period(day: date, result: PeriodTimeResult) -> DaySummaryValues:
    daily = result.daily_results[day]
    values = DaySummaryValues(
        worked_minutes=round(daily.gross_worked_seconds / 60),
        accounted_minutes=round(result.total_accounted_seconds / 60),
        expected_minutes=round(result.daily_expected_seconds[day] / 60),
        excess_minutes=round(result.total_excess_seconds / 60),
        authorized_excess_minutes=round(result.total_approved_excess_seconds / 60),
        missing_minutes=round(daily.missing_seconds / 60),
        waiver_minutes=round(daily.waiver_seconds / 60),
    )
    if any(value < 0 for value in vars(values).values()):
        raise ValueError(f"Negative apuration value for {day}")
    if values.authorized_excess_minutes > values.excess_minutes:
        raise ValueError(f"Authorized excess exceeds total excess for {day}")
    if values.accounted_minutes > values.worked_minutes:
        raise ValueError(f"Accounted time exceeds worked time for {day}")
    return values
