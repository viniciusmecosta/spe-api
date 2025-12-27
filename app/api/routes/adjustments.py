from typing import Any

from fastapi import APIRouter, Depends, Body, UploadFile, File
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.enums import AdjustmentStatus
from app.domain.models.user import User
from app.repositories.adjustment_repository import adjustment_repository
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestUpdate, AdjustmentRequestResponse, \
    AdjustmentAttachmentResponse
from app.services.adjustment_service import adjustment_service

router = APIRouter()


@router.post("/", response_model=AdjustmentRequestResponse)
def create_adjustment_request(
        request_in: AdjustmentRequestCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return adjustment_service.create_request(db, current_user.id, request_in)


@router.post("/{id}/attachments", response_model=AdjustmentAttachmentResponse)
def upload_adjustment_attachment(
        id: int,
        file: UploadFile = File(...),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Attach a document to an adjustment request.
    """
    return adjustment_service.upload_attachment(db, id, current_user.id, file)


@router.get("/my", response_model=list[AdjustmentRequestResponse])
def read_my_adjustments(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return adjustment_repository.get_all_by_user(db, current_user.id, skip, limit)


# Manager Routes

@router.get("/", response_model=list[AdjustmentRequestResponse])
def read_all_adjustments(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_repository.get_all(db, skip, limit)


@router.put("/{id}/approve", response_model=AdjustmentRequestResponse)
def approve_adjustment(
        id: int,
        comment: str = Body(None, embed=True),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.review_request(db, id, current_user.id, AdjustmentStatus.APPROVED, comment)


@router.put("/{id}/reject", response_model=AdjustmentRequestResponse)
def reject_adjustment(
        id: int,
        comment: str = Body(None, embed=True),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.review_request(db, id, current_user.id, AdjustmentStatus.REJECTED, comment)


@router.put("/{id}/edit", response_model=AdjustmentRequestResponse)
def edit_adjustment_request(
        id: int,
        request_in: AdjustmentRequestUpdate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    """
    Edit an adjustment request. (Manager only)
    """
    return adjustment_service.update_request(db, id, current_user.id, request_in)
