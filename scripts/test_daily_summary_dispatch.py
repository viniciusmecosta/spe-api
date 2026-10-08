import asyncio
import importlib
from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.features.daily_summaries.daily_summary_events import schedule_days
from app.features.daily_summaries.daily_summary_models import DailySummary


VALUE_FIELDS = (
    "worked_minutes",
    "accounted_minutes",
    "expected_minutes",
    "excess_minutes",
    "authorized_excess_minutes",
    "missing_minutes",
    "waiver_minutes",
)


async def test_dispatch() -> None:
    for module in (
        "app.features.companies.company_models",
        "app.features.printers.printer_models",
        "app.features.devices.device_models",
    ):
        importlib.import_module(module)
    async with AsyncSessionLocal() as session:
        summary = await session.scalar(
            select(DailySummary)
            .where(
                DailySummary.worked_minutes == 0,
            )
            .order_by(DailySummary.apuration_date.desc(), DailySummary.user_id)
            .limit(1)
        )
        if summary is None:
            raise RuntimeError("No empty day available for the dispatch test")
        user_id, day = summary.user_id, summary.apuration_date
        original_updated_at = summary.updated_at
        original = tuple(getattr(summary, field) for field in VALUE_FIELDS)
    schedule_days({(user_id, day)})
    for _ in range(100):
        await asyncio.sleep(0.1)
        async with AsyncSessionLocal() as session:
            current = await session.scalar(
                select(DailySummary).where(
                    DailySummary.user_id == user_id,
                    DailySummary.apuration_date == day,
                )
            )
            if current is not None and current.updated_at > original_updated_at:
                actual = tuple(getattr(current, field) for field in VALUE_FIELDS)
                if actual != original:
                    raise AssertionError((original, actual))
                print(f"OK: asynchronous recalculation completed for {day}")
                return
    raise TimeoutError(f"Daily summary was not recalculated for {day}")


if __name__ == "__main__":
    asyncio.run(test_dispatch())
