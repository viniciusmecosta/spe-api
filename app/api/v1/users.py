from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserUpdateMe
from app.schemas.work_schedule import WorkScheduleCreate, WorkSchedule
from app.services.user_service import user_service

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
def read_users(
        db: Session = Depends(deps.get_db),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        is_active: Optional[bool] = Query(None),
        role: Optional[UserRole] = Query(None),
        search: Optional[str] = Query(None),
        order_by: str = Query("id", pattern="^(id|name|username|created_at|updated_at)$"),
        order_direction: str = Query("asc", pattern="^(asc|desc)$"),
        current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    from fastapi import HTTPException, status
    from app.domain.models.enums import UserRole
    if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER] and not current_user.can_export_report:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges (Manager or Maintainer required)"
        )
    role_value = role.value if role else None
    users = user_repository.get_multi(
        db,
        skip=skip,
        limit=limit,
        is_active=is_active,
        role=role_value,
        search=search,
        order_by=order_by,
        order_direction=order_direction
    )
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
    try:
        user = user_service.create_user(db, user_in=user_in, current_user_id=current_user.id)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/me", response_model=UserResponse)
def update_user_me(
        *,
        db: Session = Depends(deps.get_db),
        user_in: UserUpdateMe,
        current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    update_data = UserUpdate(
        **user_in.model_dump(exclude_unset=True)
    )

    try:
        user = user_service.update_user(db, user_id=current_user.id, user_in=update_data,
                                        current_user_id=current_user.id)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me", response_model=UserResponse)
def read_user_me(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    can_punch_desktop = False
    can_punch_mobile = False

    if current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]:
        can_punch_desktop = True
        can_punch_mobile = True
    else:
        can_punch_desktop = current_user.can_manual_punch_desktop
        can_punch_mobile = current_user.can_manual_punch_mobile

    user_data = jsonable_encoder(current_user)
    user_data['can_manual_punch_desktop'] = can_punch_desktop
    user_data['can_manual_punch_mobile'] = can_punch_mobile

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

    if current_user.role == UserRole.MANAGER and user.role == UserRole.MAINTAINER:
        raise HTTPException(status_code=403, detail="Privilégios insuficientes para alterar este usuário")

    try:
        user = user_service.update_user(db, user_id=user_id, user_in=user_in, current_user_id=current_user.id)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{user_id}/schedules", response_model=List[WorkSchedule])
def get_historical_schedules(
        user_id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    user = user_repository.get(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user.historical_schedules

@router.post("/{user_id}/schedules", response_model=WorkSchedule)
def add_historical_schedule(
        user_id: int,
        schedule_in: WorkScheduleCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return user_service.add_historical_schedule(
        db=db, user_id=user_id, sch_data=schedule_in.model_dump(exclude_unset=True), current_user_id=current_user.id
    )

@router.put("/{user_id}/schedules/{schedule_id}", response_model=WorkSchedule)
def update_historical_schedule(
        user_id: int,
        schedule_id: int,
        schedule_in: WorkScheduleCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return user_service.update_historical_schedule(
        db=db, user_id=user_id, schedule_id=schedule_id, sch_data=schedule_in.model_dump(exclude_unset=True), current_user_id=current_user.id
    )

@router.delete("/{user_id}/schedules/{schedule_id}")
def delete_historical_schedule(
        user_id: int,
        schedule_id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    user_service.delete_historical_schedule(db=db, user_id=user_id, schedule_id=schedule_id, current_user_id=current_user.id)
    return {"detail": "Horário excluído com sucesso"}
