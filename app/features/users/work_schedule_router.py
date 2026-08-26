from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.features.users.user_models import User
from app.features.users.user_schemas import (
    BulkWorkScheduleCreate,
    BulkWorkScheduleResponse,
)
from app.features.users.user_work_schedule_service import user_work_schedule_service
from app.shared import deps
from app.shared.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.get(
    "/bulk",
    dependencies=[Depends(deps.get_current_manager)],
    responses={**FORBIDDEN_RESPONSE},
)
async def get_bulk_schedules(
    db: Annotated[Session, Depends(deps.get_db)],
    month: Annotated[int, Query(ge=1, le=12)],
    year: Annotated[int, Query(ge=2000, le=2100)],
) -> list[BulkWorkScheduleResponse]:
    return user_work_schedule_service.get_bulk_schedules(db=db, month=month, year=year)


@router.get(
    "/bulk/{valid_from}/{valid_until}",
    dependencies=[Depends(deps.get_current_manager)],
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_bulk_schedule_by_dates(
    valid_from: date,
    valid_until: date,
    db: Annotated[Session, Depends(deps.get_db)],
) -> BulkWorkScheduleResponse:
    return user_work_schedule_service.get_bulk_schedule(
        db=db, valid_from=valid_from, valid_until=valid_until
    )


@router.post(
    "/bulk",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def add_bulk_schedules(
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
    "/bulk/{valid_from}/{valid_until}",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def update_bulk_schedules(
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
    "/bulk/{valid_from}/{valid_until}",
    responses={**FORBIDDEN_RESPONSE},
)
async def delete_bulk_schedules(
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
