from dataclasses import dataclass


@dataclass(frozen=True)
class DaySummaryValues:
    worked_minutes: float
    accounted_minutes: float
    expected_minutes: float
    excess_minutes: float
    authorized_excess_minutes: float
    missing_minutes: float
    waiver_minutes: float
