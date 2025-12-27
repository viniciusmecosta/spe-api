from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.repositories.time_record_repository import time_record_repository
from app.schemas.time_record import TimeRecordResponse
from app.services.time_record_service import time_record_service

router = APIRouter()


@router.post("/entry", response_model=TimeRecordResponse)
def register_entry(
        request: Request,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_service.register_entry(db, current_user.id, request.client.host)


@router.post("/exit", response_model=TimeRecordResponse)
def register_exit(
        request: Request,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_service.register_exit(db, current_user.id, request.client.host)


@router.put("/{id}/toggle", response_model=TimeRecordResponse)
def toggle_record_type(
        id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_service.toggle_record_type(db, id, current_user.id)


@router.get("/my", response_model=list[TimeRecordResponse])
def read_my_records(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_repository.get_all_by_user(db, current_user.id, skip, limit)
