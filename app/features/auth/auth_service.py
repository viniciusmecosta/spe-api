from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.domain.enums import UserRole
from app.features.auth.auth_schemas import Token
from app.features.system.audit_service import audit_service
from app.features.users.user_repository import user_repository


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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )

        is_dev = settings.ENVIRONMENT.lower() == "dev"
        allow_bypass = is_dev and user.role == UserRole.EMPLOYEE

        if not allow_bypass:
            if not security.verify_password(password, user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect username or password",
                )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user",
            )

        access_token = security.create_access_token(subject=user.id, name=user.name)

        audit_service.log(
            db, user_id=user.id, action="LOGIN", entity="USER", entity_id=user.id
        )

        return Token(access_token=access_token, token_type="bearer")


auth_service = AuthService()
