from typing import Any, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.services.biometric_service import biometric_service

router = APIRouter()


@router.get("/available-sensor-indices", response_model=List[int])
def get_available_sensor_indices(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager),
) -> Any:
    return biometric_service.get_available_sensor_indices(db)
