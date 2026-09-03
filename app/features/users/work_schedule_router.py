from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.users.user_models import User
from app.features.users.user_schemas import (
    BulkWorkScheduleCreate,
    BulkWorkScheduleResponse,
)
from app.features.users.user_work_schedule_service import (
    UserWorkScheduleService,
    user_work_schedule_service,
)
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
        db: Annotated[AsyncSession, Depends(deps.get_async_db)],
    month: Annotated[int, Query(ge=1, le=12)],
    year: Annotated[int, Query(ge=2000, le=2100)],
        service: Annotated[UserWorkScheduleService, Depends()] = None,
) -> list[BulkWorkScheduleResponse]:
    svc = service if service is not None else user_work_schedule_service
    return await svc.get_bulk_schedules(db=db, month=month, year=year)


@router.get(
    "/bulk/{valid_from}/{valid_until}",
    dependencies=[Depends(deps.get_current_manager)],
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def get_bulk_schedule_by_dates(
    valid_from: date,
    valid_until: date,
        db: Annotated[AsyncSession, Depends(deps.get_async_db)],
        service: Annotated[UserWorkScheduleService, Depends()] = None,
) -> BulkWorkScheduleResponse:
    svc = service if service is not None else user_work_schedule_service
    return await svc.get_bulk_schedule(
        db=db, valid_from=valid_from, valid_until=valid_until
    )


@router.post(
    "/bulk",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def add_bulk_schedules(
    schedule_in: BulkWorkScheduleCreate,
    background_tasks: BackgroundTasks,
        db: Annotated[AsyncSession, Depends(deps.get_async_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
        service: Annotated[UserWorkScheduleService, Depends()] = None,
) -> Any:
    svc = service if service is not None else user_work_schedule_service
    return await svc.bulk_add_schedules(
        db=db,
        bulk_data=schedule_in.model_dump(exclude_unset=True),
        current_user_id=current_user.id,
        background_tasks=background_tasks,
    )


@router.put(
    "/bulk/{valid_from}/{valid_until}",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def update_bulk_schedules(
    valid_from: date,
    valid_until: date,
    schedule_in: BulkWorkScheduleCreate,
    background_tasks: BackgroundTasks,
        db: Annotated[AsyncSession, Depends(deps.get_async_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
        service: Annotated[UserWorkScheduleService, Depends()] = None,
) -> Any:
    svc = service if service is not None else user_work_schedule_service
    return await svc.update_bulk_schedules(
        db=db,
        old_valid_from=valid_from,
        old_valid_until=valid_until,
        bulk_data=schedule_in.model_dump(exclude_unset=True),
        current_user_id=current_user.id,
        background_tasks=background_tasks,
    )


@router.delete(
    "/bulk/{valid_from}/{valid_until}",
    responses={**FORBIDDEN_RESPONSE},
)
async def delete_bulk_schedules(
    valid_from: date,
    valid_until: date,
    background_tasks: BackgroundTasks,
        db: Annotated[AsyncSession, Depends(deps.get_async_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
        service: Annotated[UserWorkScheduleService, Depends()] = None,
) -> Any:
    svc = service if service is not None else user_work_schedule_service
    return await svc.delete_bulk_schedules(
        db=db,
        valid_from=valid_from,
        valid_until=valid_until,
        current_user_id=current_user.id,
        background_tasks=background_tasks,
    )

