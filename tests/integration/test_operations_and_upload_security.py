import httpx
import pytest
from sqlalchemy import select

from app.features.adjustments.adjustment_models import AdjustmentAttachment, AdjustmentRequest
from app.features.companies.company_models import Company
from app.features.system.job_service import JobService
from app.features.system.operations_service import OperationsService
from app.features.system.system_models import BackgroundJob
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import AdjustmentType, UserRole

pytestmark = pytest.mark.asyncio


async def test_operations_reports_real_schema_and_retry_preserves_delivered_parts(pg_session_factory):
    factory = pg_session_factory
    async with factory() as session:
        job = BackgroundJob(kind='NOTIFICATION', payload={'routine_type': 'SYNTHETIC'}, status='PARTIAL', result={
            'parts': [{'kind': 'text', 'status': 'SUCCESS', 'attempts': 1},
                      {'kind': 'document', 'status': 'FAILED', 'attempts': 4, 'filename': 'report.xlsx'}]})
        session.add(job)
        await session.commit()
        snapshot = await OperationsService(session).snapshot()
        assert snapshot['database'] == snapshot['schema'] == 'ok'
        assert snapshot['recent_jobs'][0]['id'] == job.id
        result = await JobService(session).retry(job.id)
        assert result['status'] == 'PENDING'
        assert job.result['parts'][0]['status'] == 'SUCCESS'
        assert job.result['parts'][1]['status'] == 'PENDING'
        await session.commit()


async def test_only_registered_logo_is_public_and_private_files_require_ownership(pg_session_factory, tmp_path):
    from datetime import date
    factory = pg_session_factory
    (tmp_path / 'public').mkdir()
    (tmp_path / 'public' / 'not-a-logo.txt').write_text('private')
    (tmp_path / 'legacy-logo.png').write_bytes(b'synthetic image')
    (tmp_path / 'private.pdf').write_bytes(b'synthetic attachment')
    async with factory() as session:
        owner = User(username='owner', name='Owner', role=UserRole.EMPLOYEE)
        other = User(username='other', name='Other', role=UserRole.EMPLOYEE)
        company = Company(name='Empresa sintética', cnpj='synthetic', address='Endereço', logo_path='legacy-logo.png')
        session.add_all([owner, other, company])
        await session.commit()
        adjustment = AdjustmentRequest(user_id=owner.id, adjustment_type=AdjustmentType.OTHER, target_date=date(2026, 10, 1))
        session.add(adjustment)
        await session.flush()
        session.add(AdjustmentAttachment(adjustment_request_id=adjustment.id, file_path='private.pdf', file_type='pdf'))
        await session.commit()
        adjustment_id = adjustment.id

    async def database():
        async with factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[deps.get_async_db] = database
    app.dependency_overrides[deps.get_current_active_user] = lambda: other
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/uploads/legacy-logo.png')).status_code == 200
            for path in ('/uploads/not-a-logo.txt', '/uploads/private.pdf', '/uploads/reports/secret.xlsx',
                         '/uploads/firmware/private.bin', '/uploads/.delivery_queue/1/file.log'):
                assert (await client.get(path)).status_code == 404
            assert (await client.get(f'/api/v1/adjustments/{adjustment_id}/download')).status_code == 403
            assert (await client.get('/api/v1/payroll/1/download-report')).status_code in (403, 404)
            assert (await client.get('/api/v1/firmware/download?version=v1.0.0')).status_code == 401
            assert (await client.get('/api/v1/operations')).status_code == 403
            assert (await client.get('/api/v1/routine-logs/jobs/1')).status_code == 403
            app.dependency_overrides[deps.get_current_active_user] = lambda: owner
            response = await client.get(f'/api/v1/adjustments/{adjustment_id}/download')
            assert response.status_code == 200
            assert response.content == b'synthetic attachment'
    finally:
        app.dependency_overrides.clear()
