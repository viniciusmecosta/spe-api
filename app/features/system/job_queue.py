import asyncio
import copy
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.database.session import get_async_session_context
from app.features.system.system_models import BackgroundJob, RoutineLog

logger = logging.getLogger(__name__)
TERMINAL = {'SUCCESS', 'PARTIAL', 'FAILED', 'UNCERTAIN'}
LEASE_SECONDS = 300


def utc_now():
    return datetime.now(UTC)


async def enqueue(session, kind: str, payload: dict, key: str | None = None) -> BackgroundJob:
    if key:
        existing = await session.scalar(select(BackgroundJob).where(BackgroundJob.deduplication_key == key))
        if existing:
            return existing
    job = BackgroundJob(kind=kind, payload=payload, result={}, deduplication_key=key)
    try:
        async with session.begin_nested():
            session.add(job)
            await session.flush()
    except IntegrityError:
        if not key:
            raise
        job = await session.scalar(select(BackgroundJob).where(BackgroundJob.deduplication_key == key))
        if job is None:
            raise
    return job


async def submit(kind: str, payload: dict, key: str | None = None) -> int:
    async with get_async_session_context() as session:
        job = await enqueue(session, kind, payload, key)
        return job.id


async def claim() -> dict | None:
    now = utc_now()
    async with get_async_session_context() as session:
        job = await session.scalar(
            select(BackgroundJob).where(or_(
                and_(BackgroundJob.status.in_(['PENDING', 'RETRY']), BackgroundJob.next_attempt_at <= now),
                and_(BackgroundJob.status == 'PROCESSING', BackgroundJob.lease_until <= now),
            )).order_by(BackgroundJob.next_attempt_at, BackgroundJob.id).with_for_update(skip_locked=True).limit(1)
        )
        if not job:
            return None
        job.status = 'PROCESSING'
        job.attempts += 1
        job.lease_token = uuid.uuid4().hex
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.updated_at = now
        return {'id': job.id, 'kind': job.kind, 'payload': copy.deepcopy(job.payload),
                'result': copy.deepcopy(job.result), 'token': job.lease_token, 'attempts': job.attempts}


async def checkpoint(job: dict, status: str = 'PROCESSING', delay: int = 0) -> bool:
    now = utc_now()
    async with get_async_session_context() as session:
        result = await session.execute(update(BackgroundJob).where(
            BackgroundJob.id == job['id'], BackgroundJob.lease_token == job['token'],
            BackgroundJob.status == 'PROCESSING',
        ).values(status=status, result=copy.deepcopy(job['result']), updated_at=now,
                 lease_until=now + timedelta(seconds=LEASE_SECONDS),
                 next_attempt_at=now + timedelta(seconds=delay),
                 finished_at=now if status in TERMINAL else None,
                 **({'deduplication_key': None} if status in TERMINAL and job['kind'] == 'REPROCESS' else {})))
        if result.rowcount != 1:
            return False
        if status in TERMINAL:
            target = job['payload'].get('target_date')
            from datetime import date
            session.add(RoutineLog(routine_type=job['payload'].get('routine_type', job['kind']),
                                   target_date=date.fromisoformat(target) if target else None,
                                   status=status, details=json.dumps({'job_id': job['id'], **job['result'].get('summary', {})}, ensure_ascii=False)))
    return True


async def process_once():
    job = await claim()
    if not job:
        return
    try:
        if job['kind'] == 'REPROCESS':
            from app.features.daily_summaries.daily_summary_reprocess_service import (
                process_reprocess_job,
            )
            await process_reprocess_job(job)
        else:
            from app.features.system.notification_jobs import process_notification_job
            await process_notification_job(job)
    except asyncio.CancelledError:
        
        raise
    except Exception:
        logger.exception('Falha no processamento da tarefa %s', job['id'])
        job['result']['summary'] = {'error': 'Falha interna no processamento', 'attempts': job['attempts']}
        await checkpoint(job, 'RETRY' if job['attempts'] < 4 else 'FAILED', delay=60)
