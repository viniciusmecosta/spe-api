from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.features.users.user_exceptions import (
    InsufficientPrivilegesError,
    UserAlreadyExistsError,
)
from app.features.users.user_models import User
from app.shared.enums import UserRole


class UserValidator:
    def validate_unique_fields(
        self,
        db: Session,
        *,
        username: str | None = None,
        email: str | None = None,
        cpf: str | None = None,
        current_user: User | None = None,
    ) -> None:
        if username and (not current_user or username != current_user.username):
            stmt = select(exists().where(User.username == username))
            if db.scalar(stmt):
                raise UserAlreadyExistsError("Nome de usuário já em uso.")

        if email and (not current_user or email != current_user.email):
            stmt = select(exists().where(User.email == email))
            if db.scalar(stmt):
                raise UserAlreadyExistsError("E-mail já está em uso.")

        if cpf and (not current_user or cpf != current_user.cpf):
            stmt = select(exists().where(User.cpf == cpf))
            if db.scalar(stmt):
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


user_validator = UserValidator()
