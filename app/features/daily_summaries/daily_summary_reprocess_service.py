import logging
from datetime import date, timedelta
from typing import Annotated

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.daily_summaries.daily_summary_events import recalculate_changed_days
from app.features.daily_summaries.daily_summary_reprocess_schemas import DailySummaryReprocessRequest
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service
from app.features.users.user_models import User
from app.shared import deps

logger = logging.getLogger(__name__)


class DailySummaryReprocessService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db

    async def start(
        self,
        request: DailySummaryReprocessRequest,
        background_tasks: BackgroundTasks,
        operator_id: int,
    ) -> dict[str, str]:
        assert self.db is not None
        if request.start_date > request.end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A data inicial não pode ser maior que a data final.",
            )

        month = request.start_date.replace(day=1)
        last_month = request.end_date.replace(day=1)
        while month <= last_month:
            await payroll_service.async_validate_period_open(self.db, month)
            month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)

        statement = select(User.id).order_by(User.id)
        if request.user_ids is not None:
            statement = statement.where(User.id.in_(request.user_ids))
        user_ids = list((await self.db.scalars(statement)).all())
        if request.user_ids is not None and set(user_ids) != set(request.user_ids):
            raise HTTPException(status_code=404, detail="Um ou mais funcionários não foram encontrados.")

        await audit_service.async_log_change(
            self.db,
            operator_id,
            "REPROCESS",
            entity="DAILY_SUMMARIES",
            entity_id=0,
            new_data={
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "user_ids": user_ids,
            },
        )
        background_tasks.add_task(self._run, user_ids, request.start_date, request.end_date)
        return {
            "status": "success",
            "message": "Reprocessamento dos resumos diários iniciado em segundo plano.",
        }

    async def _run(self, user_ids: list[int], start_date: date, end_date: date) -> None:
        failures = 0
        for user_id in user_ids:
            day = start_date
            while day <= end_date:
                if not await recalculate_changed_days({(user_id, day)}):
                    failures += 1
                day += timedelta(days=1)
        if failures:
            logger.error("Reprocessamento de resumos diários terminou com %s falhas", failures)
        else:
            logger.info("Reprocessamento de resumos diários concluído para %s usuários", len(user_ids))
