from typing import Annotated

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ROOT_DIR, settings
from app.features.system.system_models import BackgroundJob, RoutineLog
from app.shared import deps


class OperationsService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)]):
        self.db = db

    @staticmethod
    def expected_revision() -> str:
        config = Config(str(ROOT_DIR / 'alembic.ini'))
        config.set_main_option('script_location', str(ROOT_DIR / 'alembic'))
        return ScriptDirectory.from_config(config).get_current_head()

    async def readiness(self):
        try:
            await self.db.execute(text('SELECT 1'))
            revisions = set((await self.db.scalars(text('SELECT version_num FROM alembic_version'))).all())
            if revisions != {self.expected_revision()}:
                raise HTTPException(status_code=503, detail='Schema do banco precisa ser atualizado.')
        except SQLAlchemyError as error:
            raise HTTPException(status_code=503, detail='Banco de dados indisponível.') from error
        return {'status': 'ok', 'database': 'ok', 'schema': 'ok'}

    async def snapshot(self):
        readiness = await self.readiness()
        counts = (await self.db.execute(select(BackgroundJob.kind, BackgroundJob.status, func.count())
                  .group_by(BackgroundJob.kind, BackgroundJob.status))).all()
        pending_since = await self.db.scalar(select(func.min(BackgroundJob.created_at)).where(
            BackgroundJob.status.in_(['PENDING', 'RETRY', 'PROCESSING'])))
        logs = (await self.db.scalars(select(RoutineLog).order_by(RoutineLog.execution_time.desc()).limit(200))).all()
        latest = {}
        for log in logs:
            if log.routine_type not in latest:
                latest[log.routine_type] = {'status': log.status, 'execution_time': log.execution_time,
                                            'target_date': log.target_date, 'details': log.details}
        jobs = (await self.db.scalars(select(BackgroundJob).order_by(BackgroundJob.created_at.desc(),
                                                                   BackgroundJob.id.desc()).limit(30))).all()
        return {**readiness, 'version': settings.APP_VERSION, 'environment': settings.ENVIRONMENT,
                'timezone': settings.TIMEZONE,
                'jobs': [{'kind': kind, 'status': status, 'count': count} for kind, status, count in counts],
                'oldest_pending_at': pending_since, 'routines': latest,
                'recent_jobs': [{'id': job.id, 'kind': job.kind, 'routine_type': job.payload.get('routine_type'),
                                 'status': job.status, 'created_at': job.created_at,
                                 'progress': job.result.get('summary', {})} for job in jobs]}
