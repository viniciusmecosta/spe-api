import math
import time
from ipaddress import ip_address, ip_network

from limits import parse
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.security import get_client_ip


def is_direct_loopback(request: Request) -> bool:
    if request.client is None or any(
        name in request.headers for name in ('forwarded', 'x-forwarded-for', 'x-real-ip')
    ):
        return False
    try:
        peer = ip_address(request.client.host)
    except ValueError:
        return False
    return peer.is_loopback and not any(
        peer in ip_network(network, strict=False) for network in settings.TRUSTED_PROXY_CIDRS
    )


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.limiter = MovingWindowRateLimiter(MemoryStorage())
        self.burst_limit = parse(f'{settings.RATE_LIMIT_REQUESTS_PER_SECOND}/second')
        self.general_limit = parse(f'{settings.RATE_LIMIT_REQUESTS_PER_MINUTE}/minute')
        self.auth_limit = parse(f'{settings.RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE}/minute')

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or not settings.RATE_LIMIT_ENABLED:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if is_direct_loopback(request):
            await self.app(scope, receive, send)
            return
        path = scope['path'].rstrip('/')
        ip = get_client_ip(request)
        policies = [(self.burst_limit, 'burst'), (self.general_limit, 'general')]
        if path in {'/api/v1/auth/login', '/api/v1/auth/refresh', '/api/v1/auth/password'}:
            policies.append((self.auth_limit, 'auth'))
        for limit, name in policies:
            if not await self.limiter.hit(limit, name, ip):
                reset_at, _ = await self.limiter.get_window_stats(limit, name, ip)
                wait = max(1, math.ceil(reset_at - time.time()))
                response = JSONResponse(
                    {'detail': f'Muitas requisições. Aguarde {wait} segundos antes de tentar novamente.'},
                    status_code=429,
                    headers={'Retry-After': str(wait), 'Cache-Control': 'no-store'},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
