from datetime import date

import httpx
import pytest

from app.features.system.system_models import BackgroundJob, RoutineLog
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


async def test_jobs_and_monitoring_keep_existing_json_contracts(pg_session_factory):
    factory = pg_session_factory
    async with factory() as session:
        actor = User(username='contract-maintainer', role=UserRole.MAINTAINER, is_active=True)
        session.add(actor)
        await session.flush()
        job = BackgroundJob(kind='REPROCESS', status='PARTIAL', payload={'routine_type': 'DAILY_SUMMARIES_REPROCESS'},
                            result={'summary': {'total': 2, 'completed': 2, 'processed': 1, 'failed': 1},
                                    'failed': [{'user_id': actor.id, 'date': '2026-10-01'}]})
        notification = BackgroundJob(kind='NOTIFICATION', status='PARTIAL', payload={'routine_type': 'SYNTHETIC'},
                                     result={'summary': {'parts': 1, 'SUCCESS': 0, 'FAILED': 1, 'attempts': 2, 'error': 'Falha sintética'},
                                             'parts': [{'kind': 'email', 'status': 'FAILED', 'attempts': 2,
                                                        'to': ['private@example.com'], 'filename': 'report.xlsx',
                                                        'detail': 'Falha sintética.'}]})
        session.add_all([job, notification,
                         RoutineLog(routine_type='SYNTHETIC', status='PARTIAL', target_date=date(2026, 10, 1), details='Teste')])
        await session.commit()
        job_id, notification_id = job.id, notification.id

    async def database():
        async with factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[deps.get_async_db] = database
    app.dependency_overrides[deps.get_current_active_user] = lambda: actor
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            ready = await client.get('/api/v1/ready')
            assert ready.status_code == 200, ready.text
            assert ready.json() == {'status': 'ok', 'database': 'ok', 'schema': 'ok'}
            operations = await client.get('/api/v1/operations')
            assert operations.status_code == 200, operations.text
            assert set(operations.json()) == {'status', 'database', 'schema', 'version', 'environment', 'timezone',
                                               'jobs', 'oldest_pending_at', 'routines', 'recent_jobs'}
            detail = await client.get(f'/api/v1/routine-logs/jobs/{job_id}')
            assert detail.status_code == 200, detail.text
            payload = detail.json()
            assert set(payload) == {'id', 'kind', 'status', 'attempts', 'created_at', 'updated_at', 'finished_at',
                                    'progress', 'failures', 'parts'}
            assert payload['failures'] == [{'user_id': actor.id, 'date': '2026-10-01'}]
            delivered = await client.get(f'/api/v1/routine-logs/jobs/{notification_id}')
            assert delivered.status_code == 200, delivered.text
            assert delivered.json()['parts'] == [{'kind': 'email', 'status': 'FAILED', 'attempts': 2,
                                                   'filename': 'report.xlsx', 'detail': 'Falha sintética.'}]
            assert 'private@example.com' not in delivered.text
            retry = await client.post(f'/api/v1/routine-logs/jobs/{job_id}/retry')
            assert retry.status_code == 200, retry.text
            assert retry.json() == {'job_id': str(job_id), 'status': 'PENDING'}
            schema = (await client.get('/api/v1/openapi.json')).json()
            for path in ['/api/v1/ready', '/api/v1/operations', '/api/v1/routine-logs/jobs/{job_id}']:
                assert '$ref' in schema['paths'][path]['get']['responses']['200']['content']['application/json']['schema']
    finally:
        app.dependency_overrides.clear()
