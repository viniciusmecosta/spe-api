import argparse
import asyncio
import calendar
import importlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.recalculation_service import (
    daily_summary_recalculation_service,
)
from app.features.holidays.holiday_models import Holiday
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig


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
    for year, month in periods:
        processed = 0
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            current = date(year, month, day)
            for user_id in user_ids:
                await daily_summary_recalculation_service.calculate_day(
                    user_id, current, refresh_excess=False, allow_closed=True
                )
                processed += 1
        print(f"Processed {processed} user days for {year:04d}-{month:02d}", flush=True)


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
