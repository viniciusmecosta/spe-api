import logging
import time

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)


def _format_short_name(full_name: str) -> str:
    parts = full_name.split()
    if not parts:
        return ""
    first = parts[0]
    second = next((p for p in parts[1:] if len(p) >= 3), None)
    if second:
        return f"{first} {second}"
    return first


def _extract_user_name(request: Request) -> str:
    try:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return ""
        token = auth[7:]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        name = payload.get("name", "")
        if name:
            return _format_short_name(name)
    except Exception:
        pass
    return ""


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        host = request.client.host if request.client else "127.0.0.1"
        user_name = _extract_user_name(request)
        user_tag = f" ({user_name})" if user_name else ""
        msg = f'{host} - "{request.method} {request.url.path}" {response.status_code} {process_time:.4f}s{user_tag}'
        
        if response.status_code >= 500:
            logger.error(msg)
        elif response.status_code >= 400:
            logger.warning(msg)
        else:
            logger.info(msg)
            
        return response
