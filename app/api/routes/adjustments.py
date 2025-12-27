from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api import deps
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestResponse
from app.services.adjustment_service import adjustment_service
from app.repositories.adjustment_repository import adjustment_repository
from app.domain.models.user import User

router = APIRouter()

@router.post("/", response_model=AdjustmentRequestResponse)
def create_adjustment_request(
    request_in: AdjustmentRequestCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Create a new adjustment request (Employee).
    """
    return adjustment_service.create_request(db, current_user.id, request_in)

@router.get("/my", response_model=list[AdjustmentRequestResponse])
def read_my_adjustments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Get all adjustment requests for the current user.
    """
    return adjustment_repository.get_all_by_user(db, current_user.id, skip, limit)