from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import isDev
from app.database.session import get_async_db
from app.features.auth.auth_exceptions import InactiveUserError, InvalidCredentialsError
from app.features.auth.auth_schemas import Token
from app.features.users.user_repository import async_user_repository
from app.shared.enums import UserRole


class AuthService:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_async_db)]):
        self.db = db

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
        user = await async_user_repository.get_by_username(self.db, username=normalized_username)

        if not user:
            raise InvalidCredentialsError()

        allow_bypass = isDev() and user.role == UserRole.EMPLOYEE

        if not allow_bypass:
            if not security.verify_password(password, user.password_hash):
                raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        access_token = security.create_access_token(subject=user.id, name=user.name)
        return Token(access_token=access_token, token_type="bearer")
