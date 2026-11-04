import asyncio

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.core.config import settings
from app.middleware.rate_limit import RateLimitMiddleware, is_direct_loopback


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setattr(settings, 'RATE_LIMIT_ENABLED', True)
    monkeypatch.setattr(settings, 'RATE_LIMIT_REQUESTS_PER_SECOND', 3)
    monkeypatch.setattr(settings, 'RATE_LIMIT_REQUESTS_PER_MINUTE', 10)
    monkeypatch.setattr(settings, 'RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE', 1)
    monkeypatch.setattr(settings, 'TRUSTED_PROXY_CIDRS', [])
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.api_route('/api/v1/{path:path}', methods=['GET', 'POST', 'OPTIONS'])
    async def endpoint(path: str):
        return {'path': path}

    return app


def client(app, ip='192.0.2.1'):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(ip, 1)), base_url='http://test')


@pytest.mark.asyncio
async def test_burst_limit_separates_origins_and_recovers(application):
    async with client(application) as first, client(application, '192.0.2.2') as second:
        results = await asyncio.gather(*(first.get('/api/v1/items') for _ in range(4)))
        assert sorted(result.status_code for result in results) == [200, 200, 200, 429]
        blocked = next(result for result in results if result.status_code == 429)
        assert blocked.headers['retry-after'] == '1'
        assert blocked.headers['cache-control'] == 'no-store'
        assert (await second.get('/api/v1/items')).status_code == 200
        await asyncio.sleep(1.05)
        assert (await first.get('/api/v1/items')).status_code == 200


@pytest.mark.asyncio
async def test_hundred_concurrent_requests_respect_burst_limit(application, monkeypatch):
    monkeypatch.setattr(settings, 'RATE_LIMIT_REQUESTS_PER_SECOND', 30)
    monkeypatch.setattr(settings, 'RATE_LIMIT_REQUESTS_PER_MINUTE', 1000)
    async with client(application) as session:
        results = await asyncio.gather(*(session.get('/api/v1/items') for _ in range(100)))
    assert sum(result.status_code == 200 for result in results) == 30
    assert sum(result.status_code == 429 for result in results) == 70


@pytest.mark.asyncio
@pytest.mark.parametrize('ip', ['127.0.0.1', '::1'])
async def test_direct_localhost_is_exempt(application, ip):
    async with client(application, ip) as session:
        for _ in range(10):
            assert (await session.get('/api/v1/items')).status_code == 200


@pytest.mark.asyncio
async def test_local_proxy_does_not_bypass_external_limit(application, monkeypatch):
    monkeypatch.setattr(settings, 'TRUSTED_PROXY_CIDRS', ['127.0.0.1/32'])
    async with client(application, '127.0.0.1') as proxy:
        for _ in range(3):
            assert (await proxy.get('/api/v1/items', headers={'X-Forwarded-For': '198.51.100.1'})).status_code == 200
        assert (await proxy.get('/api/v1/items', headers={'X-Forwarded-For': '198.51.100.1'})).status_code == 429
        assert (await proxy.get('/api/v1/items', headers={'X-Forwarded-For': '198.51.100.2'})).status_code == 200
        for _ in range(3):
            assert (await proxy.get('/api/v1/items')).status_code == 200
        assert (await proxy.get('/api/v1/items')).status_code == 429


@pytest.mark.asyncio
async def test_untrusted_local_forwarded_header_is_not_exempt(application):
    async with client(application, '127.0.0.1') as session:
        for _ in range(3):
            assert (await session.get('/api/v1/items', headers={'Forwarded': 'for=198.51.100.1'})).status_code == 200
        assert (await session.get('/api/v1/items', headers={'Forwarded': 'for=198.51.100.2'})).status_code == 429


def test_direct_loopback_rejects_absent_and_invalid_peers():
    assert not is_direct_loopback(Request({'type': 'http', 'headers': []}))
    assert not is_direct_loopback(Request({'type': 'http', 'headers': [], 'client': ('invalid', 1)}))


@pytest.mark.asyncio
async def test_minute_limit_blocks_sustained_requests(application, monkeypatch):
    monkeypatch.setattr(settings, 'RATE_LIMIT_REQUESTS_PER_SECOND', 10)
    monkeypatch.setattr(settings, 'RATE_LIMIT_REQUESTS_PER_MINUTE', 3)
    async with client(application) as session:
        for _ in range(3):
            assert (await session.get('/api/v1/items')).status_code == 200
        response = await session.get('/api/v1/items')
        assert response.status_code == 429
        assert 1 <= int(response.headers['retry-after']) <= 60


@pytest.mark.asyncio
async def test_auth_limit_is_shared_across_sensitive_paths(application):
    async with client(application) as session:
        assert (await session.post('/api/v1/auth/login')).status_code == 200
        response = await session.post('/api/v1/auth/refresh/')
        assert response.status_code == 429
        assert (await session.get('/api/v1/items')).status_code == 200


@pytest.mark.asyncio
async def test_device_manager_verification_shares_auth_limit(application):
    async with client(application) as session:
        assert (await session.post('/api/v1/devices/verify-manager')).status_code == 200
        assert (await session.post('/api/v1/auth/login')).status_code == 429


@pytest.mark.asyncio
async def test_health_routes_and_other_http_requests_are_protected(application):
    async with client(application) as session:
        assert (await session.get('/api/v1/health')).status_code == 200
        assert (await session.get('/api/v1/ready')).status_code == 200
        assert (await session.options('/api/v1/items')).status_code == 200
        assert (await session.get('/api/v1/ready')).status_code == 429


@pytest.mark.asyncio
async def test_disabled_protection_allows_requests(application, monkeypatch):
    monkeypatch.setattr(settings, 'RATE_LIMIT_ENABLED', False)
    async with client(application) as session:
        for _ in range(5):
            assert (await session.get('/api/v1/items')).status_code == 200


@pytest.mark.asyncio
async def test_forwarded_ip_only_from_trusted_proxy(application, monkeypatch):
    monkeypatch.setattr(settings, 'TRUSTED_PROXY_CIDRS', ['192.0.2.10/32'])
    async with client(application, '192.0.2.10') as proxy:
        for _ in range(3):
            assert (await proxy.get('/api/v1/items', headers={'X-Forwarded-For': '198.51.100.1'})).status_code == 200
        assert (await proxy.get('/api/v1/items', headers={'X-Forwarded-For': '198.51.100.1'})).status_code == 429
        assert (await proxy.get('/api/v1/items', headers={'X-Forwarded-For': '198.51.100.2'})).status_code == 200
    async with client(application, '192.0.2.20') as attacker:
        for number in range(3):
            assert (await attacker.get('/api/v1/items', headers={'X-Forwarded-For': f'198.51.100.{number}'})).status_code == 200
        assert (await attacker.get('/api/v1/items', headers={'X-Forwarded-For': '198.51.100.9'})).status_code == 429


@pytest.mark.asyncio
async def test_non_http_is_forwarded(application):
    from unittest.mock import AsyncMock

    await application.build_middleware_stack()({'type': 'websocket', 'path': '/x', 'headers': [], 'query_string': b''}, AsyncMock(), AsyncMock())
