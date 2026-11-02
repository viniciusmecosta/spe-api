from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def to_app_timezone(value: datetime) -> datetime:
    timezone = ZoneInfo(settings.TIMEZONE)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    timezone = ZoneInfo(settings.TIMEZONE)
    start = datetime.combine(day, time.min, tzinfo=timezone)
    next_day = datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone)
    return start, next_day
