import argparse
import asyncio
import calendar
import importlib
from datetime import date, datetime, timezone

from sqlalchemy import extract, select
from sqlalchemy.dialects.postgresql import insert

from app.database.session import AsyncSessionLocal
from app.features.daily_summaries.models import DailySummary
from app.features.daily_summaries.recalculation_service import daily_summary_recalculation_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User


async def _periods() -> list[tuple[int, int]]:
    async with AsyncSessionLocal() as session:
        record_year = extract("year", TimeRecord.record_datetime)
        record_month = extract("month", TimeRecord.record_datetime)
        result = await session.execute(
            select(record_year, record_month).distinct()
            .order_by(record_year, record_month)
        )
        return [(int(year), int(month)) for year, month in result.all()]


async def mark_period(year: int, month: int) -> int:
    importlib.import_module("app.features.companies.company_models")
    importlib.import_module("app.features.printers.printer_models")
    importlib.import_module("app.features.devices.device_models")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user_ids = list((await session.scalars(select(User.id).order_by(User.id))).all())
            last_day = calendar.monthrange(year, month)[1]
            values = [
                {
                    "user_id": user_id,
                    "apuration_date": date(year, month, day),
                    "pending_recalculation": True,
                    "updated_at": datetime.now(timezone.utc),
                }
                for day in range(1, last_day + 1)
                for user_id in user_ids
            ]
            table = DailySummary.__table__
            for offset in range(0, len(values), 500):
                statement = insert(table).values(values[offset:offset + 500])
                await session.execute(statement.on_conflict_do_update(
                    constraint="uq_daily_summaries_user_date",
                    set_={
                        "pending_recalculation": True,
                        "updated_at": datetime.now(timezone.utc),
                    },
                ))
        return len(values)


async def backfill(selected: tuple[int, int] | None, execute: bool) -> None:
    periods = [selected] if selected else await _periods()
    if not execute:
        for year, month in periods:
            print(f"Would backfill {year:04d}-{month:02d}")
        return
    for year, month in periods:
        marked = await mark_period(year, month)
        print(f"Marked {marked} days for {year:04d}-{month:02d}", flush=True)
        processed = 0
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        while await daily_summary_recalculation_service.run_once(
            allow_closed=True, first_day=first, last_day=last
        ):
            processed += 1
            if processed >= marked:
                break
        async with AsyncSessionLocal() as session:
            pending = await session.scalar(
                select(DailySummary.id).where(
                    DailySummary.apuration_date >= first,
                    DailySummary.apuration_date <= last,
                    DailySummary.pending_recalculation.is_(True),
                ).limit(1)
            )
        if pending is not None:
            raise RuntimeError(f"Backfill incomplete for {year:04d}-{month:02d}")
        print(f"Processed {processed} days", flush=True)


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
