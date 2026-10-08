from datetime import date, datetime, timedelta
from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.models import DailySummary
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig

SOURCE_MODELS = (
    TimeRecord,
    AdjustmentRequest,
    UserWorkScheduleConfig,
    Holiday,
    PayrollClosure,
)
RELEVANT_FIELDS = {
    TimeRecord: ("user_id", "record_datetime", "record_type", "is_ignored", "deleted_at"),
    AdjustmentRequest: (
        "user_id", "target_date", "adjustment_type", "status", "amount_hours",
        "approved_amount_hours", "deleted_at",
    ),
    UserWorkScheduleConfig: (
        "user_id", "day_of_week", "daily_hours", "entry_1", "exit_1",
        "entry_2", "exit_2", "valid_from", "valid_until",
        "is_daily_excess_enabled",
    ),
    Holiday: ("date",),
    PayrollClosure: ("year", "month", "is_closed", "deleted_at"),
}


def _local_day(value: datetime) -> date:
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(ZoneInfo(settings.TIMEZONE)).date()


def _old_row(session: Session, source: object) -> dict | None:
    model = type(source)
    source_id = getattr(source, "id", None)
    if source_id is None:
        return None
    row = session.connection().execute(
        select(model.__table__).where(model.__table__.c.id == source_id)
    ).mappings().first()
    return dict(row) if row is not None else None


def _scope_for_record(source: TimeRecord | dict) -> tuple[int, date, date]:
    if isinstance(source, dict):
        user_id, timestamp = source["user_id"], source["record_datetime"]
    else:
        user_id, timestamp = source.user_id, source.record_datetime
    day = _local_day(timestamp)
    return user_id, day, day


def _scope_for_adjustment(source: AdjustmentRequest | dict) -> tuple[int, date, date]:
    if isinstance(source, dict):
        user_id, day = source["user_id"], source["target_date"]
    else:
        user_id, day = source.user_id, source.target_date
    return user_id, day, day


def _scope_for_schedule(
        session: Session, source: UserWorkScheduleConfig | dict
) -> tuple[int, date, date]:
    if isinstance(source, dict):
        user_id, first, last = source["user_id"], source["valid_from"], source["valid_until"]
    else:
        user_id, first, last = source.user_id, source.valid_from, source.valid_until
    if last is None:
        today = datetime.now(ZoneInfo(settings.TIMEZONE)).date()
        materialized_until = session.connection().execute(
            select(func.max(DailySummary.__table__.c.apuration_date)).where(
                DailySummary.__table__.c.user_id == user_id
            )
        ).scalar()
        ceiling = max(today, materialized_until) if materialized_until else today
        last = max(first, ceiling)
    month_start = date(first.year, first.month, 1)
    if last.month == 12:
        month_end = date(last.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(last.year, last.month + 1, 1) - timedelta(days=1)
    return user_id, month_start, month_end


def _scope_for_holiday(source: Holiday | dict) -> tuple[None, date, date]:
    day = source["date"] if isinstance(source, dict) else source.date
    return None, day, day


def _scope_for_reopening(source: PayrollClosure | dict) -> tuple[None, date, date]:
    if isinstance(source, dict):
        year, month = source["year"], source["month"]
    else:
        year, month = source.year, source.month
    first = date(year, month, 1)
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return None, first, last


def _scopes(
        session: Session, source: object, old: dict | None, deleted: bool
) -> set[tuple[int | None, date, date]]:
    result: set[tuple[int | None, date, date]] = set()
    if isinstance(source, PayrollClosure):
        if old and old["is_closed"] and (
            not source.is_closed or source.deleted_at is not None
        ):
            result.add(_scope_for_reopening(old))
        return result

    if isinstance(source, UserWorkScheduleConfig):
        if old is not None:
            result.add(_scope_for_schedule(session, old))
        if not deleted or old is None:
            result.add(_scope_for_schedule(session, source))
        return {item for item in result if item[1] <= item[2]}

    handlers = {
        TimeRecord: _scope_for_record,
        AdjustmentRequest: _scope_for_adjustment,
        Holiday: _scope_for_holiday,
    }
    handler = handlers[type(source)]
    if old is not None:
        result.add(handler(old))
    if not deleted or old is None:
        result.add(handler(source))
    return {item for item in result if item[1] <= item[2]}


def enqueue_changed_days(session: Session, flush_context: object, instances: object) -> None:
    if session.info.get("skip_daily_summary_tracking"):
        return
    if session.get_bind().dialect.name != "postgresql":
        return
    changes = set()
    schedule_changes = set()
    for source in session.new:
        if isinstance(source, SOURCE_MODELS):
            scoped = _scopes(session, source, None, False)
            changes.update(scoped)
            if isinstance(source, UserWorkScheduleConfig):
                schedule_changes.update(scoped)
    for source in session.dirty:
        if isinstance(source, SOURCE_MODELS):
            state = inspect(source)
            if any(
                state.attrs[field].history.has_changes()
                for field in RELEVANT_FIELDS[type(source)]
            ):
                scoped = _scopes(session, source, _old_row(session, source), False)
                changes.update(scoped)
                if isinstance(source, UserWorkScheduleConfig):
                    schedule_changes.update(scoped)
    for source in session.deleted:
        if isinstance(source, SOURCE_MODELS):
            scoped = _scopes(session, source, _old_row(session, source), True)
            changes.update(scoped)
            if isinstance(source, UserWorkScheduleConfig):
                schedule_changes.update(scoped)
    if not changes:
        return
    all_user_ids = None
    if any(user_id is None for user_id, _, _ in changes):
        all_user_ids = session.connection().execute(select(User.__table__.c.id)).scalars().all()
    days = set()
    for user_id, first, last in changes:
        user_ids = all_user_ids if user_id is None else [user_id]
        current = first
        while current <= last:
            days.update((current_user_id, current) for current_user_id in user_ids)
            current += timedelta(days=1)

    session.info.setdefault("daily_summary_changed_days", set()).update(days)

    if schedule_changes:
        reset_days = set()
        for user_id, first, last in schedule_changes:
            user_ids = all_user_ids if user_id is None else [user_id]
            current = first
            while current <= last:
                reset_days.update((current_user_id, current) for current_user_id in user_ids)
                current += timedelta(days=1)
        session.info.setdefault("daily_summary_reset_excess_days", set()).update(reset_days)


def register_change_tracking() -> None:
    event.listen(Session, "before_flush", enqueue_changed_days)
