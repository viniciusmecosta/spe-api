import httpx
import pytest
from sqlalchemy import func, select

from app.features.system.audit_service import AuditService
from app.features.system.system_models import AuditLog, BackgroundJob
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(('path', 'action'), [
    ('/backup/trigger', 'MANUAL_BACKUP_EMAIL'),
    ('/telegram/manual-backup', 'MANUAL_BACKUP_TELEGRAM'),
    ('/telegram/manual-report?start_date=2026-10-01&end_date=2026-10-05', 'MANUAL_REPORT_TELEGRAM'),
])
async def test_manual_operation_is_queued_with_operator_and_audit(pg_session_factory, path, action):
    async with pg_session_factory() as session:
        user = User(username='operator', name='Operador', role=UserRole.MAINTAINER)
        session.add(user)
        await session.commit()

    async def database():
        async with pg_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[deps.get_async_db] = database
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/v1' + path)
        assert response.status_code == 200
        job_id = int(response.json()['job_id'])
        async with pg_session_factory() as session:
            job = await session.get(BackgroundJob, job_id)
            audit = await session.scalar(select(AuditLog).where(AuditLog.action == action))
            assert job.status == 'PENDING'
            assert job.payload['operator_id'] == audit.user_id == user.id
            assert audit.entity_id == audit.new_data['job_id'] == job_id
            assert audit.new_data['routine_type'] == job.payload['routine_type']
    finally:
        app.dependency_overrides.clear()


async def test_manual_operation_audit_failure_rolls_back_admission(pg_session_factory, mocker):
    from app.features.system.routine_orchestrator import RoutineOrchestrator
    async with pg_session_factory() as session:
        user = User(username='operator', name='Operador', role=UserRole.MAINTAINER)
        session.add(user)
        await session.commit()
    service = RoutineOrchestrator()
    audit = AuditService()
    mocker.patch.object(audit, 'async_log', side_effect=RuntimeError('synthetic failure'))
    with pytest.raises(RuntimeError):
        await service.trigger_manual_backup_email(user, audit)
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 0
