from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Any, List

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.manual_auth_service import manual_auth_service
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
        *,
        db: Session = Depends(deps.get_db),
        user_in: UserCreate,
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    user = user_repository.get_by_username(db, username=user_in.username)
    if user:
        raise HTTPException(
            status_code=400,
            detail="O nome de usuário já existe no sistema.",
        )
    user = user_service.create_user(db, user_in=user_in, current_user_id=current_user.id)
    return user


@router.put("/me", response_model=UserResponse)
def update_user_me(
        *,
        db: Session = Depends(deps.get_db),
        password: str = Body(None),
        name: str = Body(None),
        current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    current_user_data = jsonable_encoder(current_user)
    user_in = UserUpdate(**current_user_data)
    if password is not None:
        user_in.password = password
    if name is not None:
        user_in.name = name

    user = user_repository.update(db, db_obj=current_user, obj_in=user_in)
    return user


@router.get("/me", response_model=UserResponse)
def read_user_me(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    can_punch = False

    if current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]:
        can_punch = True
    elif current_user.can_manual_punch:
        can_punch = True
    else:
        can_punch = manual_auth_service.check_authorization(db, current_user.id)

    user_data = jsonable_encoder(current_user)
    user_data['can_manual_punch'] = can_punch

    return user_data


@router.get("/{user_id}", response_model=UserResponse)
def read_user_by_id(
        user_id: int,
        current_user: User = Depends(deps.get_current_active_user),
        db: Session = Depends(deps.get_db),
) -> Any:
    user = user_repository.get(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if user.id != current_user.id and current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
        raise HTTPException(status_code=400, detail="Privilégios insuficientes")

    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
        *,
        db: Session = Depends(deps.get_db),
        user_id: int,
        user_in: UserUpdate,
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    user = user_repository.get(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user = user_repository.update(db, db_obj=user, obj_in=user_in)
    return user