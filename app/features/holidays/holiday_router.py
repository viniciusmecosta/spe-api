from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.features.holidays.holiday_schemas import HolidayCreate, HolidayResponse
from app.features.holidays.holiday_service import holiday_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **AUTH_RESPONSES},
)
async def create_holiday(
        holiday_in: HolidayCreate,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> HolidayResponse:
    return holiday_service.create_holiday(db, holiday_in, current_user.id)


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_active_user)],
)
async def read_holidays(
        db: Annotated[Session, Depends(deps.get_db)],
) -> list[HolidayResponse]:
    return holiday_service.get_all_holidays(db)


@router.delete(
    "/{id}",
    responses={**BAD_REQUEST_RESPONSE, **AUTH_RESPONSES},
)
async def delete_holiday(
        id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> dict[str, str]:
    return holiday_service.delete_holiday(db, id, current_user.id)
