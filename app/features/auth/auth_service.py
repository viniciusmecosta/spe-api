import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import is_dev, settings
from app.core.exceptions import DomainException
from app.database.session import get_async_db
from app.features.auth.auth_exceptions import InactiveUserError, InvalidCredentialsError
from app.features.auth.auth_models import RefreshToken
from app.features.auth.auth_repository import auth_repository
from app.features.auth.auth_schemas import Token
from app.features.users.user_models import User
from app.features.users.user_repository import async_user_repository
from app.shared.enums import UserRole

TIMING_EQUALIZER_HASH = "$2b$12$CPxM9UaNMltN9hwmyiJg8uQIy2HcDU9aVpmi4/sozyLhAZ3eIdbIa"


class AuthService:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_async_db)]):
        self.db = db

    def _issue_tokens(
        self,
        user: User,
        *,
        family_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> Token:
        now = datetime.now(UTC)
        requires_change = user.password_change_required is True
        if requires_change:
            lifetime = settings.PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES * 60
            return Token(
                access_token=security.create_access_token(
                    subject=user.id,
                    name=user.name,
                    auth_version=user.auth_version or 0,
                    purpose="password_change",
                    expires_delta=timedelta(seconds=lifetime),
                ),
                expires_in=lifetime,
                password_change_required=True,
            )
        family_id = family_id or secrets.token_hex(16)
        expires_at = expires_at or now + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        raw_token = secrets.token_urlsafe(48)
        auth_repository.add(
            self.db,
            RefreshToken(
                user_id=user.id,
                token_hash=security.get_api_key_hash(raw_token),
                family_id=family_id,
                auth_version=user.auth_version or 0,
                created_at=now,
                expires_at=expires_at,
            ),
        )
        return Token(
            access_token=security.create_access_token(
                subject=user.id,
                name=user.name,
                auth_version=user.auth_version or 0,
                session_id=family_id,
            ),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=raw_token,
            refresh_expires_in=max(0, int((expires_at - now).total_seconds())),
        )

    async def authenticate(
        self,
        username: str = "",
        password: str = "",
        *,
        form_data: Any = None,
        request: Request | None = None,
    ) -> Token:
        if form_data is not None:
            username = form_data.username
            password = form_data.password
        normalized_username = username.lower()
        if request is not None:
            request.state.attempted_user = normalized_username
        user = await async_user_repository.get_by_username(
            self.db, username=normalized_username
        )
        if not user:
            await asyncio.to_thread(
                security.verify_password, password, TIMING_EQUALIZER_HASH
            )
            raise InvalidCredentialsError()
        allow_bypass = (
            is_dev()
            and user.role == UserRole.EMPLOYEE
            and user.password_change_required is not True
        )
        if not allow_bypass and not await asyncio.to_thread(
            security.verify_password, password, user.password_hash
        ):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveUserError()
        token = self._issue_tokens(user)
        await self.db.commit()
        return token

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    async def _locked_refresh(self, raw_token: str) -> tuple[User | None, RefreshToken]:
        token_hash = security.get_api_key_hash(raw_token)
        token = await auth_repository.find_refresh(self.db, token_hash)
        if token is None:
            raise InvalidCredentialsError()
        user = await auth_repository.lock_user(self.db, token.user_id)
        token = await auth_repository.find_refresh(self.db, token_hash)
        if token is None:
            raise InvalidCredentialsError()
        return user, token

    async def refresh(self, raw_token: str) -> Token:
        user, token = await self._locked_refresh(raw_token)
        now = datetime.now(UTC)
        invalid = (
            token.revoked_at is not None
            or token.used_at is not None
            or self._utc(token.expires_at) <= now
            or user is None
            or not user.is_active
            or user.password_change_required is True
            or token.auth_version != (user.auth_version or 0)
        )
        if invalid:
            await auth_repository.revoke_family(self.db, token.family_id, now)
            await self.db.commit()
            raise InvalidCredentialsError()
        token.used_at = now
        result = self._issue_tokens(
            user, family_id=token.family_id, expires_at=self._utc(token.expires_at)
        )
        await self.db.commit()
        return result

    async def logout(self, raw_token: str) -> None:
        token = await auth_repository.find_refresh(
            self.db, security.get_api_key_hash(raw_token)
        )
        if token is not None:
            await auth_repository.lock_user(self.db, token.user_id)
            await auth_repository.revoke_family(
                self.db, token.family_id, datetime.now(UTC)
            )
            await self.db.commit()

    async def change_password(
        self, current_user: User, current_password: str, new_password: str
    ) -> Token:
        previous_version = current_user.auth_version
        user = await auth_repository.lock_user(self.db, current_user.id)
        if user is None or not user.is_active or user.auth_version != previous_version:
            raise InvalidCredentialsError()
        if not await asyncio.to_thread(
            security.verify_password, current_password, user.password_hash
        ):
            raise InvalidCredentialsError()
        if await asyncio.to_thread(
            security.verify_password, new_password, user.password_hash
        ):
            raise DomainException(
                status_code=422,
                detail="A nova senha deve ser diferente da senha atual.",
            )
        user.password_hash = await asyncio.to_thread(
            security.get_password_hash, new_password
        )
        user.password_change_required = False
        user.auth_version = (user.auth_version or 0) + 1
        await auth_repository.revoke_user(self.db, user.id, datetime.now(UTC))
        token = self._issue_tokens(user)
        await self.db.commit()
        return token
