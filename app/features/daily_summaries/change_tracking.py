from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

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


def _scope_for_schedule(source: UserWorkScheduleConfig | dict) -> tuple[int, date, date]:
    if isinstance(source, dict):
        user_id, first, last = source["user_id"], source["valid_from"], source["valid_until"]
    else:
        user_id, first, last = source.user_id, source.valid_from, source.valid_until
    return user_id, first, last or datetime.now(ZoneInfo(settings.TIMEZONE)).date()


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


def _scopes(source: object, old: dict | None, deleted: bool) -> set[tuple[int | None, date, date]]:
    result: set[tuple[int | None, date, date]] = set()
    if isinstance(source, PayrollClosure):
        if old and old["is_closed"] and (
            not source.is_closed or source.deleted_at is not None
        ):
            result.add(_scope_for_reopening(old))
        return result

    handlers = {
        TimeRecord: _scope_for_record,
        AdjustmentRequest: _scope_for_adjustment,
        UserWorkScheduleConfig: _scope_for_schedule,
        Holiday: _scope_for_holiday,
    }
    handler = handlers[type(source)]
    if old is not None:
        result.add(handler(old))
    if not deleted:
        result.add(handler(source))
    return {item for item in result if item[1] <= item[2]}


def enqueue_changed_days(session: Session, flush_context: object, instances: object) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    changes = set()
    for source in session.new:
        if isinstance(source, SOURCE_MODELS):
            changes.update(_scopes(source, None, False))
    for source in session.dirty:
        if isinstance(source, SOURCE_MODELS) and session.is_modified(source, include_collections=False):
            changes.update(_scopes(source, _old_row(session, source), False))
    for source in session.deleted:
        if isinstance(source, SOURCE_MODELS):
            changes.update(_scopes(source, _old_row(session, source), True))
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

    table = DailySummary.__table__
    now = datetime.now(ZoneInfo("UTC"))
    ordered_days = sorted(days)
    for offset in range(0, len(ordered_days), 500):
        batch = ordered_days[offset:offset + 500]
        statement = insert(table).values([
            {
                "user_id": user_id,
                "apuration_date": day,
                "pending_recalculation": True,
                "updated_at": now,
            }
            for user_id, day in batch
        ])
        session.connection().execute(
            statement.on_conflict_do_update(
                constraint="uq_daily_summaries_user_date",
                set_={
                    "pending_recalculation": True,
                    "updated_at": now,
                },
            )
        )


def register_change_tracking() -> None:
    event.listen(Session, "before_flush", enqueue_changed_days)
