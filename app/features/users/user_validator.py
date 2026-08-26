from typing import Annotated

from fastapi import Depends
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.features.users.user_exceptions import (
    InsufficientPrivilegesError,
    UserAlreadyExistsError,
)
from app.features.users.user_models import User
from app.shared.enums import UserRole


class UserValidator:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_async_db)]):
        self.db = db

    async def validate_unique_fields(
        self,
        *,
        username: str | None = None,
        email: str | None = None,
        cpf: str | None = None,
        current_user: User | None = None,
    ) -> None:
        if username and (not current_user or username != current_user.username):
            stmt = select(exists().where(User.username == username))
            if await self.db.scalar(stmt):
                raise UserAlreadyExistsError("Nome de usuário já em uso.")

        if email and (not current_user or email != current_user.email):
            stmt = select(exists().where(User.email == email))
            if await self.db.scalar(stmt):
                raise UserAlreadyExistsError("E-mail já está em uso.")

        if cpf and (not current_user or cpf != current_user.cpf):
            stmt = select(exists().where(User.cpf == cpf))
            if await self.db.scalar(stmt):
                raise UserAlreadyExistsError("CPF já está em uso.")

    def validate_manager_privilege(self, current_user: User, target_user: User) -> None:
        if current_user.role == UserRole.MANAGER and target_user.role == UserRole.MAINTAINER:
            raise InsufficientPrivilegesError("Privilégios insuficientes para edição.")

    def validate_read_privilege(self, current_user: User, target_user: User) -> None:
        if target_user.id != current_user.id and current_user.role not in [
            UserRole.MANAGER,
            UserRole.MAINTAINER,
        ]:
            raise InsufficientPrivilegesError("Privilégios insuficientes.")
