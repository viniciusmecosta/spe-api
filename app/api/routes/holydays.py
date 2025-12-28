from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api import deps
from app.schemas.holiday import HolidayCreate, HolidayResponse
from app.repositories.holiday_repository import holiday_repository
from app.domain.models.user import User

router = APIRouter()

@router.post("/", response_model=HolidayResponse)
def create_holiday(
    holiday_in: HolidayCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return holiday_repository.create(db, holiday_in)

@router.get("/", response_model=list[HolidayResponse])
def read_holidays(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return holiday_repository.get_all(db)

@router.delete("/{id}")
def delete_holiday(
    id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    holiday_repository.delete(db, id)
    return {"status": "success"}