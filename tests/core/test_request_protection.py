import logging

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.core.logger import CleanFormatter
from app.middleware.request_logging import RequestLoggingMiddleware
from app.core.request_context import request_id


@pytest.mark.asyncio
async def test_request_id_is_propagated_sanitized_and_cleared():
    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)

    @application.get('/')
    async def endpoint():
        formatter = CleanFormatter('%(message)s')
        record = logging.LogRecord('test', logging.INFO, '', 0, 'message', (), None)
        return {'id': request_id.get(), 'log': formatter.format(record)}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
        response = await client.get('/', headers={'X-Request-ID': 'review_123'})
        assert response.headers['X-Request-ID'] == response.json()['id'] == 'review_123'
        assert 'request_id=' not in response.json()['log']
        response = await client.get('/', headers={'X-Request-ID': '<invalid>'})
        assert response.headers['X-Request-ID'] != '<invalid>'
    assert request_id.get() is None


@pytest.mark.asyncio
async def test_total_request_body_is_limited_even_without_content_length():
    application = FastAPI()
    application.add_middleware(RequestBodyLimitMiddleware, max_body_size=10)

    @application.post('/')
    async def endpoint(request: Request):
        return {'size': len(await request.body())}

    async def chunks():
        yield b'123456'
        yield b'789012'

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
        response = await client.post('/', content=chunks())
        assert response.status_code == 413
        assert (await client.post('/', content=b'123')).json() == {'size': 3}


@pytest.mark.asyncio
async def test_unexpected_error_keeps_request_id_without_exposing_internal_details():
    from app.core.exceptions import setup_exception_handlers

    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)
    setup_exception_handlers(application)

    @application.get('/')
    async def endpoint():
        raise RuntimeError('private internal exception')

    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/', headers={'X-Request-ID': 'failed_request'})
        assert response.status_code == 500
        assert response.headers['X-Request-ID'] == 'failed_request'
        assert 'private internal exception' not in response.text
