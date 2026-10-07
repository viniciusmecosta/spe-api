from dataclasses import asdict
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.daily_summaries.calculator import DaySummaryValues
from app.features.daily_summaries.models import DailySummary


class DailySummaryRepository:
    async def upsert(
        self, session: AsyncSession, user_id: int, day: date, values: DaySummaryValues
    ) -> None:
        table = DailySummary.__table__
        update_values = asdict(values)
        update_values["updated_at"] = datetime.now(timezone.utc)
        statement = insert(table).values(
            user_id=user_id, apuration_date=day, **update_values
        )
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_daily_summaries_user_date", set_=update_values
            )
        )

    async def get_range(
        self, session: AsyncSession, user_id: int, first: date, last: date
    ) -> list[DailySummary]:
        result = await session.scalars(
            select(DailySummary)
            .where(
                DailySummary.user_id == user_id,
                DailySummary.apuration_date >= first,
                DailySummary.apuration_date <= last,
            )
            .order_by(DailySummary.apuration_date)
        )
        return list(result.all())

daily_summary_repository = DailySummaryRepository()
