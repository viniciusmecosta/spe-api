from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.features.holidays.holiday_schemas import HolidayCreate, HolidayResponse
from app.features.holidays.holiday_service import HolidayService
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
        service: Annotated[HolidayService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> HolidayResponse:
    return service.create_holiday(holiday_in=holiday_in, current_user_id=current_user.id)


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_active_user)],
)
async def read_holidays(
        service: Annotated[HolidayService, Depends()],
) -> list[HolidayResponse]:
    return service.get_all_holidays()


@router.delete(
    "/{id}",
    responses={**BAD_REQUEST_RESPONSE, **AUTH_RESPONSES},
)
async def delete_holiday(
        id: int,
        service: Annotated[HolidayService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> dict[str, str]:
    return service.delete_holiday(holiday_id=id, current_user_id=current_user.id)
