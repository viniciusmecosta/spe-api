import io
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.features.companies.company_models import Company
from app.features.companies.company_service import CompanyService
from app.features.devices.device_models import Firmware
from app.features.devices.firmware_service import FirmwareService
from app.features.payroll.payroll_models import PayrollClosure
from app.features.payroll.payroll_service import PayrollService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole
from fastapi import UploadFile

pytestmark = pytest.mark.asyncio


def logo_content():
    content = io.BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(content, format='PNG')
    return content.getvalue()


async def seed_upload_owner(factory):
    async with factory() as session:
        owner = User(username='upload-admin', name='Admin', role=UserRole.MAINTAINER)
        company = Company(name='Empresa', cnpj='11222333000181', address='Endereço', logo_path='old.png')
        session.add_all([owner, company])
        await session.commit()
        closure = PayrollClosure(month=6, year=2026, closed_by_user_id=owner.id, report_path='reports/old.xlsx')
        session.add(closure)
        await session.commit()
        return owner, closure.id


async def test_http_uploads_validate_content_and_preserve_download_contract(pg_session_factory, tmp_path, monkeypatch):
    owner, closure_id = await seed_upload_owner(pg_session_factory)
    (tmp_path / 'old.png').write_bytes(b'original logo')

    async def database():
        async with pg_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[deps.get_async_db] = database
    app.dependency_overrides[deps.get_current_active_user] = lambda: owner
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            invalid = await client.post('/api/v1/companies/logo', files={'file': ('logo.png', b'text', 'image/png')})
            assert invalid.status_code == 400
            assert (tmp_path / 'old.png').exists()
            logo = await client.post('/api/v1/companies/logo', files={'file': ('logo.png', logo_content(), 'image/png')})
            assert logo.status_code == 200
            assert not (tmp_path / 'old.png').exists()
            public = await client.get(logo.json()['logo_path'])
            assert public.status_code == 200
            assert public.content == logo_content()
            monkeypatch.setattr(settings, 'UPLOAD_FIRMWARE_MAX_BYTES', 8)
            oversized = await client.post('/api/v1/firmware/upload', data={'version': 'v1.0.0'},
                                          files={'file': ('firmware.bin', b'123456789', 'application/octet-stream')})
            assert oversized.status_code == 413
            firmware = await client.post('/api/v1/firmware/upload', data={'version': 'v1.0.0'},
                                         files={'file': ('firmware.bin', b'12345678', 'application/octet-stream')})
            assert firmware.status_code == 201
            updated = await client.put('/api/v1/firmware/v1.0.0',
                                       files={'file': ('firmware.bin', b'updated', 'application/octet-stream')})
            assert updated.status_code == 200
            report = await client.post(f'/api/v1/payroll/{closure_id}/legacy-report',
                                       files={'file': ('report.csv', b'name,hours\nAna,8', 'text/csv')})
            assert report.status_code == 200
            invalid = await client.post(f'/api/v1/payroll/{closure_id}/legacy-report',
                                        files={'file': ('report.xlsx', b'invalid', 'application/octet-stream')})
            assert invalid.status_code == 400
            downloaded = await client.get(f'/api/v1/payroll/{closure_id}/download-report')
            assert downloaded.status_code == 200
            assert downloaded.content == b'name,hours\nAna,8'
        async with pg_session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(Firmware)) == 2
        assert not list(tmp_path.rglob('.upload_*'))
    finally:
        app.dependency_overrides.clear()


async def test_logo_commit_failure_preserves_previous_reference_and_file(pg_session_factory, tmp_path, mocker):
    owner, _ = await seed_upload_owner(pg_session_factory)
    (tmp_path / 'old.png').write_bytes(b'original logo')
    async with pg_session_factory() as session:
        mocker.patch.object(session, 'commit', new_callable=AsyncMock, side_effect=RuntimeError('injected failure'))
        with pytest.raises(RuntimeError, match='injected failure'):
            await CompanyService(session).upload_logo(
                file=UploadFile(filename='logo.png', file=io.BytesIO(logo_content())), current_user_id=owner.id)
    async with pg_session_factory() as session:
        company = await session.scalar(select(Company))
        assert company.logo_path == 'old.png'
    assert (tmp_path / 'old.png').read_bytes() == b'original logo'
    assert list((tmp_path / 'public').iterdir()) == []


@pytest.mark.parametrize('category', ['firmware', 'legacy'])
async def test_failed_commit_does_not_leave_reference_or_new_upload(pg_session_factory, tmp_path, mocker, category):
    owner, closure_id = await seed_upload_owner(pg_session_factory)
    async with pg_session_factory() as session:
        mocker.patch.object(session, 'commit', new_callable=AsyncMock, side_effect=RuntimeError('injected failure'))
        with pytest.raises(RuntimeError, match='injected failure'):
            if category == 'firmware':
                await FirmwareService(session).upload_firmware(version='v1.0.0',
                    file=UploadFile(filename='firmware.bin', file=io.BytesIO(b'firmware')), current_user_id=owner.id)
            else:
                await PayrollService(session).upload_legacy_report(closure_id=closure_id,
                    upload_file=UploadFile(filename='report.csv', file=io.BytesIO(b'name,hours\nAna,8')))
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Firmware)) == 0
        closure = await session.get(PayrollClosure, closure_id)
        assert closure.report_path == 'reports/old.xlsx'
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]
