from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.user_service import user_service

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
def read_users(
        db: Session = Depends(deps.get_db),
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    users = user_repository.get_multi(db, skip=skip, limit=limit)
    return users


@router.post("/", response_model=UserResponse)
def create_user(
        user_in: UserCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    return user_service.create_user(db, user_in, current_user.id)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
        user_id: int,
        user_in: UserUpdate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    return user_service.update_user(db, user_id, user_in, current_user.id)


@router.patch("/{user_id}/disable", response_model=UserResponse)
def disable_user(
        user_id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    return user_service.disable_user(db, user_id, current_user.id)


@router.get("/{user_id}", response_model=UserResponse)
def read_user_by_id(
        user_id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    user = user_repository.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
