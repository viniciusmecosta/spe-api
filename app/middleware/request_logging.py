import logging
import re
import time
import uuid

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.core.request_context import request_context
from app.utils.formatters import format_short_name

logger = logging.getLogger(__name__)


def _extract_user_name(request: Request) -> str:
    name = ""
    try:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            name = payload.get("name", "")
    except (jwt.PyJWTError, ValueError, TypeError):
        name = ""

    if not name:
        name = getattr(request.state, "attempted_user", "")

    if name:
        return format_short_name(name)

    return getattr(request.state, "device_name", "")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        supplied = request.headers.get('X-Request-ID', '')
        correlation = supplied if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', supplied) else uuid.uuid4().hex
        request.state.request_id = correlation
        with request_context(correlation):
            return await self._dispatch_logged(request, call_next, correlation)

    async def _dispatch_logged(self, request: Request, call_next, correlation: str) -> Response:
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception('Falha ao processar %s %s', request.method, request.url.path)
            raise
        response.headers['X-Request-ID'] = correlation
        process_time = time.perf_counter() - start_time
        host = request.client.host if request.client else '127.0.0.1'
        user_name = _extract_user_name(request)
        user_tag = f' ({user_name})' if user_name else ''
        ntp_tag = ' - NTP ERROR' if getattr(request.state, 'ntp_error', False) else ''
        msg = f'{host} - "{request.method} {request.url.path}" {response.status_code} {process_time:.4f}s{user_tag}{ntp_tag}'
        if response.status_code >= 500:
            logger.error(msg)
        elif response.status_code >= 400:
            logger.warning(msg)
        else:
            logger.info(msg)
        return response
