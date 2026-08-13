from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.services.biometric_service import biometric_service

router = APIRouter()


@router.get(
    "/available-sensor-indices",
    dependencies=[Depends(deps.get_current_manager)],
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def get_available_sensor_indices(
    db: Annotated[Session, Depends(deps.get_db)],
) -> list[int]:
    return biometric_service.get_available_sensor_indices(db)
