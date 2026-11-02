import argparse
import asyncio
import calendar
import importlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_service import (
    daily_summary_service,
)
from app.features.holidays.holiday_models import Holiday
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared.enums import AdjustmentType
from app.shared.work_schedule_time import minutes_to_seconds


async def _periods() -> list[tuple[int, int]]:
    async with AsyncSessionLocal() as session:
        first_record = await session.scalar(
            select(func.min(TimeRecord.__table__.c.record_datetime))
        )
        first_adjustment = await session.scalar(
            select(func.min(AdjustmentRequest.__table__.c.target_date))
        )
        first_schedule = await session.scalar(
            select(func.min(UserWorkScheduleConfig.__table__.c.valid_from))
        )
        first_holiday = await session.scalar(select(func.min(Holiday.__table__.c.date)))
    candidates = [
        value.astimezone(ZoneInfo(settings.TIMEZONE)).date()
        if isinstance(value, datetime) else value
        for value in (first_record, first_adjustment, first_schedule, first_holiday)
        if value is not None
    ]
    if not candidates:
        return []
    first = min(candidates).replace(day=1)
    last = datetime.now(ZoneInfo(settings.TIMEZONE)).date().replace(day=1)
    periods = []
    while first <= last:
        periods.append((first.year, first.month))
        first = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return periods


async def report_excess_differences(year: int, month: int, last_day: int) -> None:
    first = date(year, month, 1)
    last = date(year, month, last_day)
    statement = (
        select(DailySummary.user_id, DailySummary.apuration_date, DailySummary.excess_minutes,
               AdjustmentRequest.id, AdjustmentRequest.status, AdjustmentRequest.amount_hours,
               AdjustmentRequest.approved_amount_hours)
        .outerjoin(AdjustmentRequest, and_(
            AdjustmentRequest.user_id == DailySummary.user_id,
            AdjustmentRequest.target_date == DailySummary.apuration_date,
            AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        ))
        .where(DailySummary.apuration_date >= first, DailySummary.apuration_date <= last)
        .order_by(DailySummary.apuration_date, DailySummary.user_id, AdjustmentRequest.id)
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(statement)).all()
    differences = 0
    for user_id, day, excess_minutes, adjustment_id, status, amount_hours, approved_hours in rows:
        calculated = int(minutes_to_seconds(excess_minutes) / 60)
        registered = int(minutes_to_seconds((amount_hours or 0) * 60) / 60) if adjustment_id is not None else 0
        approved = int(minutes_to_seconds(approved_hours * 60) / 60) if approved_hours is not None else None
        if calculated == registered and (approved is None or approved <= calculated):
            continue
        differences += 1
        print(
            f"Excedente para revisão: usuário={user_id}, data={day}, "
            f"ajuste={adjustment_id or 'ausente'}, status={status.value if status else 'ausente'}, "
            f"minutos_registrados={registered}, minutos_aprovados={approved}, minutos_apurados={calculated}",
            flush=True,
        )
    print(
        f"Conferência de excedentes {year:04d}-{month:02d}: {differences} divergências. "
        "Nenhuma aprovação foi alterada; revise as divergências antes da liberação.",
        flush=True,
    )


async def backfill(selected: tuple[int, int] | None, execute: bool) -> None:
    periods = [selected] if selected else await _periods()
    if not execute:
        for year, month in periods:
            print(f"Would backfill {year:04d}-{month:02d}")
        return
    for module in (
        "app.features.companies.company_models",
        "app.features.printers.printer_models",
        "app.features.devices.device_models",
    ):
        importlib.import_module(module)
    async with AsyncSessionLocal() as session:
        user_ids = list((await session.scalars(select(User.id).order_by(User.id))).all())
    today = datetime.now(ZoneInfo(settings.TIMEZONE)).date()
    for year, month in periods:
        processed = 0
        last_day = calendar.monthrange(year, month)[1]
        if (year, month) == (today.year, today.month):
            last_day = today.day
        for day in range(1, last_day + 1):
            current = date(year, month, day)
            for user_id in user_ids:
                await daily_summary_service.calculate_day(
                    user_id, current, refresh_excess=False, allow_closed=True
                )
                processed += 1
        print(f"Processed {processed} user days for {year:04d}-{month:02d}", flush=True)
        await report_excess_differences(year, month, last_day)


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize legacy daily summaries")
    parser.add_argument("--period", help="Period in YYYY-MM format")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    selected = None
    if args.period:
        try:
            year, month = map(int, args.period.split("-"))
            date(year, month, 1)
            selected = year, month
        except ValueError as error:
            parser.error(f"Invalid --period: {error}")
    asyncio.run(backfill(selected, args.execute))


if __name__ == "__main__":
    main()
