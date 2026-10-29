from io import BytesIO
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select

from app.features.companies.company_models import Company
from app.features.devices.device_models import Firmware
from app.features.system.audit_service import audit_service
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


def synthetic_logo():
    image = BytesIO()
    Image.new('RGB', (3, 3), 'blue').save(image, format='PNG')
    return image.getvalue()


@pytest.mark.parametrize('operation', ['logo', 'firmware'])
async def test_upload_audit_failure_rolls_back_row_and_removes_new_file(pg_session_factory, tmp_path,
                                                                       monkeypatch, operation):
    async with pg_session_factory() as session:
        actor = User(username='configuration-admin', name='Gestor Sintetico', role=UserRole.MAINTAINER)
        company = Company(name='Empresa Sintetica', cnpj='11222333000181', address='Endereco Sintetico',
                          logo_path='old.png')
        session.add_all([actor, company])
        await session.commit()
        company_id = company.id
    public = tmp_path / 'public'
    public.mkdir()
    old_logo = public / 'old.png'
    old_logo.write_bytes(synthetic_logo())
    monkeypatch.setattr(audit_service, 'async_log_change', AsyncMock(side_effect=RuntimeError('Auditoria indisponivel')))
    app.dependency_overrides[deps.get_current_maintainer] = lambda: actor
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url='http://test') as client:
            if operation == 'logo':
                response = await client.post('/api/v1/companies/logo',
                                             files={'file': ('new.png', synthetic_logo(), 'image/png')})
            else:
                response = await client.post('/api/v1/firmware/upload', data={'version': 'v1.0.0'},
                                             files={'file': ('new.bin', b'Synthetic firmware', 'application/octet-stream')})
        assert response.status_code == 500
        async with pg_session_factory() as session:
            assert (await session.get(Company, company_id)).logo_path == 'old.png'
            assert await session.scalar(select(func.count()).select_from(Firmware)) == 0
        assert list(public.iterdir()) == [old_logo]
        assert list((tmp_path / 'firmware').glob('*')) == []
    finally:
        app.dependency_overrides.clear()


async def test_firmware_update_audit_failure_keeps_previous_version(pg_session_factory, tmp_path, monkeypatch):
    async with pg_session_factory() as session:
        actor = User(username='firmware-admin', name='Gestor Sintetico', role=UserRole.MAINTAINER)
        firmware = Firmware(version='v1.0.0', file_path='firmware/old.bin')
        session.add_all([actor, firmware])
        await session.commit()
    directory = tmp_path / 'firmware'
    directory.mkdir()
    old = directory / 'old.bin'
    old.write_bytes(b'previous firmware')
    monkeypatch.setattr(audit_service, 'async_log_change', AsyncMock(side_effect=RuntimeError('Auditoria indisponivel')))
    app.dependency_overrides[deps.get_current_maintainer] = lambda: actor
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url='http://test') as client:
            response = await client.put('/api/v1/firmware/v1.0.0',
                                        files={'file': ('new.bin', b'Synthetic firmware', 'application/octet-stream')})
        assert response.status_code == 500
        async with pg_session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(Firmware)) == 1
        assert list(directory.iterdir()) == [old]
        assert old.read_bytes() == b'previous firmware'
    finally:
        app.dependency_overrides.clear()


async def test_firmware_response_failure_rolls_back_and_removes_binary(pg_session_factory, tmp_path, monkeypatch):
    from app.features.devices.device_schemas import FirmwareResponse

    async with pg_session_factory() as session:
        actor = User(username='response-admin', name='Gestor Sintetico', role=UserRole.MAINTAINER)
        session.add(actor)
        await session.commit()
    def invalid_response(*_args, **_kwargs):
        raise ValueError('Resposta sintetica invalida')

    monkeypatch.setattr(FirmwareResponse, 'model_validate', invalid_response)
    app.dependency_overrides[deps.get_current_maintainer] = lambda: actor
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url='http://test') as client:
            response = await client.post('/api/v1/firmware/upload', data={'version': 'v1.0.0'},
                                         files={'file': ('new.bin', b'Synthetic firmware', 'application/octet-stream')})
        assert response.status_code == 500
        async with pg_session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(Firmware)) == 0
        assert list((tmp_path / 'firmware').glob('*')) == []
    finally:
        app.dependency_overrides.clear()
