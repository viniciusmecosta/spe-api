from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

DOCUMENT_VERIFICATION_REQUEST_LIMIT = 257 * 1024 * 1024


class PathBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int):
        self.normal = RequestBodyLimitMiddleware(app, max_body_size=max_body_size)
        self.document_verification = RequestBodyLimitMiddleware(
            app, max_body_size=max(max_body_size, DOCUMENT_VERIFICATION_REQUEST_LIMIT),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/api/v1/documents/verify" and scope["method"] == "POST":
            await self.document_verification(scope, receive, send)
        else:
            await self.normal(scope, receive, send)
