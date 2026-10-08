from datetime import date, timedelta

from app.shared.enums import DayOfWeek


def format_day_groups(days: list[int]) -> str:
    if not days:
        return ""
    days = sorted(set(days))

    blocks = []
    current_block = [days[0]]
    for day in days[1:]:
        if day == current_block[-1] + 1:
            current_block.append(day)
        else:
            blocks.append(current_block)
            current_block = [day]
    blocks.append(current_block)

    parts = []
    for block in blocks:
        if len(block) >= 3:
            parts.append(f"{DayOfWeek(block[0]).abreviado} a {DayOfWeek(block[-1]).abreviado}")
        elif len(block) == 2:
            parts.append(f"{DayOfWeek(block[0]).abreviado} e {DayOfWeek(block[1]).abreviado}")
        else:
            parts.append(DayOfWeek(block[0]).abreviado)

    if len(parts) > 1:
        return ", ".join(parts[:-1]) + " e " + parts[-1]
    return parts[0]


def get_schedule_transitions(user, start_date: date, end_date: date) -> list[date]:
    transitions = {start_date, end_date + timedelta(days=1)}
    for schedule in user.historical_schedules:
        if schedule.valid_from and start_date <= schedule.valid_from <= end_date:
            transitions.add(schedule.valid_from)
        if schedule.valid_until and start_date <= schedule.valid_until <= end_date:
            transitions.add(schedule.valid_until + timedelta(days=1))
    return sorted(transitions)


def group_schedules_by_period(user, transitions: list[date]) -> list[tuple[date, date, list]]:
    periods = []
    for index in range(len(transitions) - 1):
        period_start = transitions[index]
        period_end = transitions[index + 1] - timedelta(days=1)
        if period_start > period_end:
            continue
        active_schedules = []
        for schedule in user.historical_schedules:
            if schedule.valid_from <= period_end and (
                not schedule.valid_until or schedule.valid_until >= period_start
            ):
                active_schedules.append(schedule)
        periods.append((period_start, period_end, active_schedules))
    return periods


def format_schedule_time_interval(schedule) -> str | None:
    if not schedule.entry_1 and not schedule.entry_2 and not schedule.exit_1 and not schedule.exit_2:
        return None
    parts = []
    if schedule.entry_1 and schedule.exit_1:
        parts.append(f"{schedule.entry_1.strftime('%H:%M')} às {schedule.exit_1.strftime('%H:%M')}")
    if schedule.entry_2 and schedule.exit_2:
        parts.append(f"{schedule.entry_2.strftime('%H:%M')} às {schedule.exit_2.strftime('%H:%M')}")
    return " e ".join(parts) if parts else None


def group_schedules_by_interval(schedules) -> dict[str, list[int]]:
    grouped = {}
    for schedule in schedules:
        time_interval = format_schedule_time_interval(schedule)
        if time_interval:
            grouped.setdefault(time_interval, []).append(schedule.day_of_week)
    return grouped
