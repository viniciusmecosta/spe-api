from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api import deps
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.user_service import user_service
from app.repositories.user_repository import user_repository
from app.domain.models.user import User

router = APIRouter()

@router.get("/", response_model=list[UserResponse])
def read_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager),
) -> Any:
    """
    Retrieve users. (Manager only)
    """
    return user_repository.get_multi(db, skip=skip, limit=limit)

@router.post("/", response_model=UserResponse)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager),
) -> Any:
    """
    Create new user. (Manager only)
    """
    return user_service.create_user(db, user_in, current_user.id)

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager),
) -> Any:
    """
    Update a user. (Manager only)
    """
    return user_service.update_user(db, user_id, user_in, current_user.id)

@router.patch("/{user_id}/disable", response_model=UserResponse)
def disable_user(
    user_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager),
) -> Any:
    """
    Disable a user. (Manager only)
    """
    return user_service.disable_user(db, user_id, current_user.id)