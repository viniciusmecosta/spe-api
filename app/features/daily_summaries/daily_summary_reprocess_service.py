import hashlib
import json
import logging
from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.daily_summaries.daily_summary_events import recalculate_changed_days
from app.features.daily_summaries.daily_summary_reprocess_schemas import (
    DailySummaryReprocessRequest,
)
from app.features.payroll.payroll_service import payroll_service
from app.features.system.audit_service import audit_service
from app.features.system.job_queue import checkpoint, enqueue
from app.features.users.user_models import User
from app.shared import deps

logger = logging.getLogger(__name__)


class DailySummaryReprocessService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db

    async def start(
        self,
        request: DailySummaryReprocessRequest,
        operator_id: int,
    ) -> dict[str, str]:
        assert self.db is not None
        if request.start_date > request.end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A data inicial não pode ser maior que a data final.",
            )

        day_count = (request.end_date - request.start_date).days + 1
        if day_count > settings.REPROCESS_MAX_DAYS:
            raise HTTPException(status_code=422, detail=f'O período deve ter no máximo {settings.REPROCESS_MAX_DAYS} dias.')
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

        if day_count * len(user_ids) > settings.REPROCESS_MAX_ITEMS:
            raise HTTPException(status_code=422, detail='A quantidade de dias e usuários excede o limite do reprocessamento.')
        scope = {'user_ids': sorted(user_ids), 'start_date': str(request.start_date), 'end_date': str(request.end_date)}
        key = 'REPROCESS:' + hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        job = await enqueue(self.db, 'REPROCESS', {
            'routine_type': 'DAILY_SUMMARIES_REPROCESS', 'user_ids': user_ids,
            'start_date': request.start_date.isoformat(), 'end_date': request.end_date.isoformat(),
            'operator_id': operator_id, 'target_date': request.end_date.isoformat(),
        }, key)
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

        return {
            "status": "success",
            "job_id": str(job.id),
            "status_url": f"/api/v1/routine-logs/jobs/{job.id}",
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


async def process_reprocess_job(job: dict) -> None:
    payload = job['payload']
    start, end = date.fromisoformat(payload['start_date']), date.fromisoformat(payload['end_date'])
    days = (end - start).days + 1
    users = payload['user_ids']
    retry_items = payload.get('retry_items')
    total = len(retry_items) if retry_items is not None else len(users) * days
    progress = job['result']
    progress.setdefault('cursor', 0)
    progress.setdefault('processed', 0)
    progress.setdefault('failed', [])
    batch_end = min(total, progress['cursor'] + settings.REPROCESS_BATCH_SIZE)
    while progress['cursor'] < batch_end:
        index = progress['cursor']
        if retry_items is not None:
            user_id = retry_items[index]['user_id']
            day = date.fromisoformat(retry_items[index]['date'])
        else:
            user_id = users[index // days]
            day = start + timedelta(days=index % days)
        succeeded = await recalculate_changed_days({(user_id, day)})
        if succeeded:
            progress['processed'] += 1
        else:
            progress['failed'].append({'user_id': user_id, 'date': day.isoformat()})
        progress['cursor'] += 1
        progress['summary'] = {'total': total, 'completed': progress['cursor'],
                               'processed': progress['processed'], 'failed': len(progress['failed'])}
        if not await checkpoint(job):
            return
    finished = progress['cursor'] == total
    final_status = 'SUCCESS'
    if progress['failed']:
        final_status = 'PARTIAL' if progress['processed'] else 'FAILED'
    await checkpoint(job, final_status if finished else 'RETRY', delay=0)
