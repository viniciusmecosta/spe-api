from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.domain.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import audit_service


class UserService:
    def create_user(self, db: Session, user_in: UserCreate, current_user_id: int) -> User:
        user = user_repository.get_by_email(db, email=user_in.email)
        if user:
            raise HTTPException(
                status_code=400,
                detail="The user with this email already exists in the system.",
            )

        user_in.password = get_password_hash(user_in.password)
        created_user = user_repository.create(db, user_in)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="CREATE",
            entity="USER",
            entity_id=created_user.id,
            details=f"Created user {created_user.email}"
        )
        return created_user

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        if user_in.password:
            user_in.password = get_password_hash(user_in.password)

        updated_user = user_repository.update(db, user, user_in)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="UPDATE",
            entity="USER",
            entity_id=updated_user.id,
            details="Updated user profile"
        )
        return updated_user

    def disable_user(self, db: Session, user_id: int, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updated_user = user_repository.update(db, user, {"is_active": False})

        audit_service.log(
            db,
            user_id=current_user_id,
            action="DISABLE",
            entity="USER",
            entity_id=updated_user.id,
            details="Disabled user"
        )
        return updated_user


user_service = UserService()
