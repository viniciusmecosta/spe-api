from datetime import UTC, datetime

from app.database.session import get_async_session_context
from app.features.auth.auth_repository import auth_repository


async def purge_expired_refresh_tokens() -> int:
    async with get_async_session_context() as session:
        return await auth_repository.purge_expired(session, datetime.now(UTC))
