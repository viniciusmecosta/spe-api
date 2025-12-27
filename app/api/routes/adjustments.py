from typing import Any
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from app.api import deps
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestResponse
from app.services.adjustment_service import adjustment_service
from app.repositories.adjustment_repository import adjustment_repository
from app.domain.models.user import User
from app.domain.models.enums import AdjustmentStatus

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

# Manager Routes

@router.get("/", response_model=list[AdjustmentRequestResponse])
def read_all_adjustments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    """
    Get all adjustment requests (Manager only).
    """
    return adjustment_repository.get_all(db, skip, limit)

@router.put("/{id}/approve", response_model=AdjustmentRequestResponse)
def approve_adjustment(
    id: int,
    comment: str = Body(None, embed=True),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    """
    Approve an adjustment request.
    """
    return adjustment_service.review_request(db, id, current_user.id, AdjustmentStatus.APPROVED, comment)

@router.put("/{id}/reject", response_model=AdjustmentRequestResponse)
def reject_adjustment(
    id: int,
    comment: str = Body(None, embed=True),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    """
    Reject an adjustment request.
    """
    return adjustment_service.review_request(db, id, current_user.id, AdjustmentStatus.REJECTED, comment)