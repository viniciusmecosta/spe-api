from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_schemas import DaySummaryValues


class DailySummaryRepository:
    async def get_by_date(
        self, session: Any, user_id: int, target_date: date
    ) -> DailySummary | None:
        statement = select(DailySummary).where(
            DailySummary.user_id == user_id,
            DailySummary.apuration_date == target_date,
        )
        if hasattr(session, "sync_session"):
            return await session.scalar(statement)
        return session.scalar(statement)

    async def get_range(
        self, session: Any, user_id: int, first: date, last: date
    ) -> list[DailySummary]:
        statement = (
            select(DailySummary)
            .where(
                DailySummary.user_id == user_id,
                DailySummary.apuration_date >= first,
                DailySummary.apuration_date <= last,
            )
            .order_by(DailySummary.apuration_date)
        )
        if hasattr(session, "sync_session"):
            result = await session.scalars(statement)
        else:
            result = session.scalars(statement)
        return list(result.all())

    async def upsert(
        self, session: Any, user_id: int, target_date: date, values: DaySummaryValues
    ) -> None:
        table = DailySummary.__table__
        update_values = asdict(values)
        update_values["updated_at"] = datetime.now(timezone.utc)
        statement = (
            insert(table)
            .values(user_id=user_id, apuration_date=target_date, **update_values)
            .on_conflict_do_update(
                constraint="uq_daily_summaries_user_date",
                set_=update_values,
            )
        )
        if hasattr(session, "sync_session"):
            await session.execute(statement)
        else:
            session.execute(statement)


daily_summary_repository = DailySummaryRepository()
