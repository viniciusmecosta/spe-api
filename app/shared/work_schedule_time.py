from datetime import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def minutes_to_seconds(minutes: Any) -> float:
    rounded = Decimal(str(minutes)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(rounded * 60)


def _legacy_schedule_seconds(schedule: Any) -> float:
    return minutes_to_seconds(getattr(schedule, 'daily_minutes', 0) or 0)


def _parse_time(value: Any) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        try:
            return time.fromisoformat(value)
        except ValueError:
            return None
    return None


def shift_duration_seconds(start: Any, end: Any) -> float | None:
    entry = _parse_time(start)
    exit_time = _parse_time(end)
    if entry is None or exit_time is None:
        return None
    entry_seconds = entry.hour * 3600 + entry.minute * 60
    exit_seconds = exit_time.hour * 3600 + exit_time.minute * 60
    return (exit_seconds - entry_seconds) % 86400


def schedule_expected_seconds(schedule: Any | None) -> float:
    if schedule is None:
        return 0.0
    intervals = [
        (getattr(schedule, 'entry_1', None), getattr(schedule, 'exit_1', None)),
        (getattr(schedule, 'entry_2', None), getattr(schedule, 'exit_2', None)),
    ]
    complete = []
    for entry, exit_time in intervals:
        if entry is None and exit_time is None:
            continue
        duration = shift_duration_seconds(entry, exit_time)
        if duration is None:
            return _legacy_schedule_seconds(schedule)
        complete.append(duration)
    if complete:
        return sum(complete)
    return _legacy_schedule_seconds(schedule)
