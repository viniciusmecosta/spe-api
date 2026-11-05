from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.auth_models import RefreshToken
from app.features.users.user_models import User


class AuthRepository:
    async def find_refresh(
        self, db: AsyncSession, token_hash: str
    ) -> RefreshToken | None:
        return await db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .execution_options(populate_existing=True)
        )

    async def lock_user(self, db: AsyncSession, user_id: int) -> User | None:
        return await db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def revoke_family(
        self, db: AsyncSession, family_id: str, now: datetime
    ) -> None:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
            )
            .values(revoked_at=now)
        )

    async def revoke_user(self, db: AsyncSession, user_id: int, now: datetime) -> None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def purge_expired(
        self, db: AsyncSession, now: datetime, batch_size: int = 1000
    ) -> int:
        expired = (
            select(RefreshToken.id)
            .where(RefreshToken.expires_at <= now)
            .order_by(
                RefreshToken.expires_at,
                RefreshToken.id,
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(
            delete(RefreshToken).where(RefreshToken.id.in_(expired))
        )
        return result.rowcount

    def add(self, db: AsyncSession, token: RefreshToken) -> None:
        db.add(token)


auth_repository = AuthRepository()
