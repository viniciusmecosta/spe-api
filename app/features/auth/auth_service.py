from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.features.auth.auth_exceptions import InactiveUserError, InvalidCredentialsError
from app.features.auth.auth_schemas import Token
from app.features.system.audit_service import audit_service
from app.features.users.user_repository import user_repository
from app.shared.enums import UserRole


class AuthService:
    def authenticate(
            self,
            db: Session,
            username: str,
            password: str,
    ) -> Token:
        normalized_username = username.lower()
        user = user_repository.get_by_username(db, username=normalized_username)

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
        audit_service.log(db, user.id, "LOGIN", entity="USER", entity_id=user.id)
        return Token(access_token=access_token, token_type="bearer")


auth_service = AuthService()
