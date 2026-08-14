from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.holiday import HolidayCreate, HolidayResponse
from app.services.holiday_service import holiday_service

router = APIRouter()


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Já existe um feriado cadastrado para esta data ou período fechado"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def create_holiday(
    holiday_in: HolidayCreate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> HolidayResponse:
    return holiday_service.create_holiday(db, holiday_in, current_user.id)


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_active_user)],
    responses={
        401: {"description": "Não autenticado"},
    },
)
def read_holidays(
    db: Annotated[Session, Depends(deps.get_db)],
) -> list[HolidayResponse]:
    return holiday_service.get_all_holidays(db)


@router.delete(
    "/{id}",
    responses={
        400: {"description": "Período fechado"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def delete_holiday(
    id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> dict[str, str]:
    return holiday_service.delete_holiday(db, id, current_user.id)
