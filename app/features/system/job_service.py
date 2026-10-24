from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared import deps


class JobService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)]):
        self.db = db

    async def get(self, job_id: int):
        from fastapi import HTTPException
    
        from app.features.system.system_models import BackgroundJob
        job = await self.db.get(BackgroundJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='Tarefa não encontrada.')
        return {'id': job.id, 'kind': job.kind, 'status': job.status, 'attempts': job.attempts,
                'created_at': job.created_at, 'updated_at': job.updated_at,
                'finished_at': job.finished_at, 'progress': job.result.get('summary', {}),
                'failures': job.result.get('failed', []),
                'parts': [{'kind': part['kind'], 'status': part['status'], 'attempts': part['attempts'],
                           'filename': part.get('filename'), 'detail': part.get('detail')}
                          for part in job.result.get('parts', [])]}

    async def retry(self, job_id: int):
        from fastapi import HTTPException
        from sqlalchemy import select
        from app.features.system.job_queue import utc_now
        from app.features.system.system_models import BackgroundJob
        job = await self.db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update())
        if job is None:
            raise HTTPException(status_code=404, detail='Tarefa não encontrada.')
        if job.status not in ('FAILED', 'PARTIAL'):
            raise HTTPException(status_code=409, detail='A tarefa precisa estar encerrada com falha para tentar novamente.')
        result = dict(job.result)
        if job.kind == 'REPROCESS' and result.get('failed'):
            job.payload = {**job.payload, 'retry_items': result['failed']}
            result = {}
        else:
            parts = []
            for original in result.get('parts', []):
                part = dict(original)
                if part['status'] in ('FAILED', 'PARTIAL'):
                    part.update(status='PENDING', attempts=0, retry_at=0)
                parts.append(part)
            if parts and not any(part['status'] == 'PENDING' for part in parts):
                raise HTTPException(status_code=409, detail='Há entregas incertas; confira o destino antes de reenviar manualmente.')
            if parts:
                result['parts'] = parts
        job.result = result
        job.status = 'PENDING'
        job.attempts = 0
        job.finished_at = None
        job.next_attempt_at = utc_now()
        return {'job_id': str(job.id), 'status': job.status}
