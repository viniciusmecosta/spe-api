from typing import Annotated

from app.api import deps
from app.api.openapi_responses import AUTH_RESPONSES
from app.services.biometric_service import biometric_service
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/available-sensor-indices",
    dependencies=[Depends(deps.get_current_manager)],
)
def get_available_sensor_indices(
        db: Annotated[Session, Depends(deps.get_db)],
) -> list[int]:
    return biometric_service.get_available_sensor_indices(db)
