from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.database.session import get_async_db
from app.features.auth.auth_exceptions import InactiveUserError, InvalidCredentialsError
from app.features.auth.auth_schemas import Token
from app.features.system.audit_service import audit_service
from app.features.users.user_repository import async_user_repository
from app.shared.enums import UserRole


class AuthService:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_async_db)]):
        self.db = db

    async def authenticate(
            self,
            username: str,
            password: str,
    ) -> Token:
        normalized_username = username.lower()
        user = await async_user_repository.get_by_username(self.db, username=normalized_username)

        if not user:
            raise InvalidCredentialsError()

        is_dev = settings.ENVIRONMENT.lower() == "dev"
        allow_bypass = is_dev and user.role == UserRole.EMPLOYEE

        if not allow_bypass:
            if not security.verify_password(password, user.password_hash):
                raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        access_token = security.create_access_token(subject=user.id, name=user.name)
        await audit_service.async_log(self.db, user.id, "LOGIN", entity="USER", entity_id=user.id)
        return Token(access_token=access_token, token_type="bearer")
