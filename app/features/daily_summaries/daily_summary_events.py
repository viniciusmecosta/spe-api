import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DailySummaryRecalculationError
from app.database.payroll_lock import lock_payroll_periods
from app.features.payroll.payroll_exceptions import PayrollPeriodClosedError
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig

logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()
_sync_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daily-summary")
_dispatch_loop: asyncio.AbstractEventLoop | None = None

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


def bind_dispatch_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _dispatch_loop
    _dispatch_loop = loop


async def recalculate_changed_days(
    days: set[tuple[int, date]],
    reset_excess_days: set[tuple[int, date]] | None = None,
) -> bool:
    from app.features.daily_summaries.daily_summary_service import (
        daily_summary_service,
    )

    reset_days = reset_excess_days or set()
    succeeded = True
    for user_id, day in sorted(days, key=lambda item: (item[1], item[0])):
        reset = (user_id, day) in reset_days
        for attempt in range(3):
            try:
                await daily_summary_service.recalculate_day(
                    user_id, day, reset_excess=reset
                )
                break
            except Exception:
                logger.exception(
                    "Daily summary recalculation failed for user %s on %s", user_id, day
                )
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    succeeded = False
    return succeeded


def schedule_days(
    days: set[tuple[int, date]],
    reset_excess_days: set[tuple[int, date]] | None = None,
) -> asyncio.Task[bool] | None:
    if not days:
        return
    reset_days = reset_excess_days or set()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        if _dispatch_loop is not None and _dispatch_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                recalculate_changed_days(days, reset_days), _dispatch_loop
            )
            return
        _sync_executor.submit(asyncio.run, recalculate_changed_days(days, reset_days))
        return
    task = loop.create_task(recalculate_changed_days(days, reset_days))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def _after_commit(session: Session) -> None:
    _after_rollback(session)


def _before_commit(session: Session) -> None:
    if session.info.get("skip_daily_summary_tracking"):
        return
    session.flush()
    days = set(session.info.get("daily_summary_changed_days", set()))
    reset_days = set(session.info.get("daily_summary_reset_excess_days", set()))
    if not days:
        return
    from app.features.daily_summaries.daily_summary_service import daily_summary_service

    session.info["skip_daily_summary_tracking"] = True
    try:
        for user_id, day in sorted(days, key=lambda item: (item[1], item[0])):
            daily_summary_service.calculate_in_session(
                session, user_id, day, reset_excess=(user_id, day) in reset_days
            )
        session.flush()
    except Exception as exc:
        raise DailySummaryRecalculationError() from exc
    finally:
        session.info.pop("skip_daily_summary_tracking", None)


def _after_rollback(session: Session) -> None:
    session.info.pop("daily_summary_changed_days", None)
    session.info.pop("daily_summary_reset_excess_days", None)


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
    return user_id, first, last


def _schedule_day_scopes(
    session: Session, source: UserWorkScheduleConfig | dict
) -> set[tuple[int, date, date]]:
    user_id, first, last = _scope_for_schedule(session, source)
    day_of_week = source["day_of_week"] if isinstance(source, dict) else source.day_of_week
    current = first + timedelta(days=(day_of_week - first.weekday()) % 7)
    result = set()
    while current <= last:
        result.add((user_id, current, current))
        current += timedelta(days=7)
    return result


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
    if isinstance(source, PayrollClosure):
        return _reopening_scopes(source, old)
    if isinstance(source, UserWorkScheduleConfig):
        return _schedule_scopes(session, source, old, deleted)
    handler = _scope_handler(source)
    return _source_scopes(source, old, deleted, handler) if handler else set()


def _reopening_scopes(source: PayrollClosure, old: dict | None) -> set[tuple[None, date, date]]:
    is_reopening = old and old["is_closed"] and (
        not source.is_closed or source.deleted_at is not None
    )
    return {_scope_for_reopening(old)} if is_reopening else set()


def _schedule_scopes(session, source, old, deleted):
    result = set(_schedule_day_scopes(session, old)) if old is not None else set()
    if old is None or not deleted:
        result.update(_schedule_day_scopes(session, source))
    return {item for item in result if item[1] <= item[2]}


def _scope_handler(source):
    for model, handler in (
        (TimeRecord, _scope_for_record),
        (AdjustmentRequest, _scope_for_adjustment),
        (Holiday, _scope_for_holiday),
    ):
        if isinstance(source, model):
            return handler
    return None


def _source_scopes(source, old, deleted, handler):
    result = {handler(old)} if old is not None else set()
    if old is None or not deleted:
        result.add(handler(source))
    return {item for item in result if item[1] <= item[2]}


def _collect_changes(session: Session, sources, *, deleted: bool = False):
    changes = set()
    schedule_changes = set()
    for source in sources:
        if not isinstance(source, SOURCE_MODELS):
            continue
        old = _old_row(session, source) if deleted else None
        if not deleted and source in session.dirty:
            state = inspect(source)
            relevant = any(
                state.attrs[field].history.has_changes()
                for field in RELEVANT_FIELDS[type(source)]
            )
            if not relevant:
                continue
            old = _old_row(session, source)
        scoped = _scopes(session, source, old, deleted)
        changes.update(scoped)
        if isinstance(source, UserWorkScheduleConfig):
            schedule_changes.update(scoped)
    return changes, schedule_changes


def _expand_scopes(scopes, all_user_ids):
    days = set()
    for user_id, first, last in scopes:
        user_ids = all_user_ids if user_id is None else [user_id]
        current = first
        while current <= last:
            days.update((current_user_id, current) for current_user_id in user_ids)
            current += timedelta(days=1)
    return days


def enqueue_changed_days(session: Session, flush_context: object, instances: object) -> None:
    if session.info.get("skip_daily_summary_tracking"):
        return
    if session.get_bind().dialect.name != "postgresql":
        return
    new_changes, new_schedule_changes = _collect_changes(session, session.new)
    dirty_changes, dirty_schedule_changes = _collect_changes(session, session.dirty)
    deleted_changes, deleted_schedule_changes = _collect_changes(
        session, session.deleted, deleted=True
    )
    changes = new_changes | dirty_changes | deleted_changes
    schedule_changes = new_schedule_changes | dirty_schedule_changes | deleted_schedule_changes
    closure_periods = {
        (source.year, source.month)
        for source in (*session.new, *session.dirty, *session.deleted)
        if isinstance(source, PayrollClosure)
    }
    if not changes:
        if closure_periods:
            lock_payroll_periods(session, closure_periods, exclusive=True)
        return
    all_user_ids = None
    if any(user_id is None for user_id, _, _ in changes):
        all_user_ids = session.connection().execute(select(User.__table__.c.id)).scalars().all()
    days = _expand_scopes(changes, all_user_ids)

    periods = {(day.year, day.month) for _, day in days}
    periods.update(closure_periods)
    if lock_payroll_periods(session, periods, exclusive=bool(closure_periods)):
        closed = session.connection().execute(
            select(PayrollClosure.__table__.c.year, PayrollClosure.__table__.c.month).where(
                PayrollClosure.is_closed.is_(True), PayrollClosure.deleted_at.is_(None),
            )
        ).all()
        mutations, removed = changes, set()
        if closure_periods:
            mutations, _ = _collect_changes(
                session, [source for source in (*session.new, *session.dirty)
                          if not isinstance(source, PayrollClosure)],
            )
            removed, _ = _collect_changes(
                session, [source for source in session.deleted
                          if not isinstance(source, PayrollClosure)], deleted=True,
            )
        mutation_periods = {
            (day.year, day.month) for _, day in _expand_scopes(mutations | removed, all_user_ids)
        }
        if mutation_periods.intersection(closed):
            raise PayrollPeriodClosedError("A competência foi fechada; a alteração não foi gravada.")

    session.info.setdefault("daily_summary_changed_days", set()).update(days)

    if schedule_changes:
        reset_days = _expand_scopes(schedule_changes, all_user_ids)
        session.info.setdefault("daily_summary_reset_excess_days", set()).update(reset_days)


def register_daily_summary_events() -> None:
    for name, listener in (
        ("before_flush", enqueue_changed_days), ("before_commit", _before_commit),
        ("after_commit", _after_commit), ("after_rollback", _after_rollback),
    ):
        if not event.contains(Session, name, listener):
            event.listen(Session, name, listener)


register_change_tracking = register_daily_summary_events
register_daily_summary_dispatch = register_daily_summary_events
