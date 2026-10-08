from dataclasses import dataclass


@dataclass(frozen=True)
class DaySummaryValues:
    worked_minutes: int
    accounted_minutes: int
    expected_minutes: int
    excess_minutes: int
    authorized_excess_minutes: int
    missing_minutes: int
    waiver_minutes: int
