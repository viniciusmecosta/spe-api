from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate
from app.domain.models.user import User
from app.core.security import get_password_hash


class UserService:
    def create_user(self, db: Session, user_in: UserCreate) -> User:
        user = user_repository.get_by_email(db, email=user_in.email)
        if user:
            raise HTTPException(
                status_code=400,
                detail="The user with this email already exists in the system.",
            )

        # Hash password
        user_in.password = get_password_hash(user_in.password)
        return user_repository.create(db, user_in)

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        if user_in.password:
            user_in.password = get_password_hash(user_in.password)

        return user_repository.update(db, user, user_in)

    def disable_user(self, db: Session, user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user_repository.update(db, user, {"is_active": False})


user_service = UserService()