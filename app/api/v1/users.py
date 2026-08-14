from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.api.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate, UserUpdateMe
from app.schemas.work_schedule import (
    BulkWorkScheduleCreate,
    BulkWorkScheduleResponse,
)
from app.services.user_service import user_service
from app.services.user_work_schedule_service import user_work_schedule_service

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.get(
    "/",
    responses={**FORBIDDEN_RESPONSE},
)
def read_users(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: bool | None = Query(None),
    role: UserRole | None = Query(None),
    search: str | None = Query(None),
    order_by: str = Query("id", pattern="^(id|name|username|created_at|updated_at)$"),
    order_direction: str = Query("asc", pattern="^(asc|desc)$"),
) -> list[UserResponse]:
    role_value = role.value if role else None
    return user_service.get_multi(
        db,
        skip=skip,
        limit=limit,
        is_active=is_active,
        role=role_value,
        search=search,
        order_by=order_by,
        order_direction=order_direction,
    )


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
def create_user(
    user_in: UserCreate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> UserResponse:
    return user_service.create_user(db, user_in=user_in, current_user_id=current_user.id)


@router.put(
    "/me",
    responses={**BAD_REQUEST_RESPONSE},
)
def update_user_me(
    user_in: UserUpdateMe,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    update_data = UserUpdate(**user_in.model_dump(exclude_unset=True))
    return user_service.update_user(
        db,
        user_id=current_user.id,
        user_in=update_data,
        current_user_id=current_user.id,
    )


@router.get("/me")
def read_user_me(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    return user_service.get_user_me(current_user)


@router.get(
    "/bulk-schedules",
    dependencies=[Depends(deps.get_current_manager)],
    responses={**FORBIDDEN_RESPONSE},
)
def get_bulk_schedules(
    db: Annotated[Session, Depends(deps.get_db)],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
) -> list[BulkWorkScheduleResponse]:
    return user_work_schedule_service.get_bulk_schedules(db=db, month=month, year=year)


@router.get(
    "/bulk-schedules/{valid_from}/{valid_until}",
    dependencies=[Depends(deps.get_current_manager)],
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
def get_bulk_schedule_by_dates(
    valid_from: date,
    valid_until: date,
    db: Annotated[Session, Depends(deps.get_db)],
) -> BulkWorkScheduleResponse:
    return user_work_schedule_service.get_bulk_schedule(
        db=db, valid_from=valid_from, valid_until=valid_until
    )


@router.post(
    "/bulk-schedules",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
def add_bulk_schedules(
    schedule_in: BulkWorkScheduleCreate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> Any:
    return user_work_schedule_service.bulk_add_schedules(
        db=db,
        bulk_data=schedule_in.model_dump(exclude_unset=True),
        current_user_id=current_user.id,
    )


@router.put(
    "/bulk-schedules/{valid_from}/{valid_until}",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
def update_bulk_schedules(
    valid_from: date,
    valid_until: date,
    schedule_in: BulkWorkScheduleCreate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> Any:
    return user_work_schedule_service.update_bulk_schedules(
        db=db,
        old_valid_from=valid_from,
        old_valid_until=valid_until,
        bulk_data=schedule_in.model_dump(exclude_unset=True),
        current_user_id=current_user.id,
    )


@router.delete(
    "/bulk-schedules/{valid_from}/{valid_until}",
    responses={**FORBIDDEN_RESPONSE},
)
def delete_bulk_schedules(
    valid_from: date,
    valid_until: date,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> Any:
    return user_work_schedule_service.delete_bulk_schedules(
        db=db,
        valid_from=valid_from,
        valid_until=valid_until,
        current_user_id=current_user.id,
    )


@router.get(
    "/{user_id}",
    responses={**BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)
def read_user_by_id(
    user_id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    return user_service.get_user_by_id(db, user_id=user_id, current_user=current_user)


@router.put(
    "/{user_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> UserResponse:
    return user_service.update_user_by_admin(
        db, user_id=user_id, user_in=user_in, current_user=current_user
    )
