from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any

from app.api import deps
from app.domain.models.user import User
from app.repositories.holiday_repository import holiday_repository
from app.schemas.holiday import HolidayCreate, HolidayResponse
from app.services.audit_service import audit_service

router = APIRouter()


@router.post("/", response_model=HolidayResponse)
def create_holiday(
        holiday_in: HolidayCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    holiday = holiday_repository.create(db, holiday_in)
    audit_service.log(
        db, actor_id=current_user.id, action="CREATE", entity="HOLIDAY", entity_id=holiday.id,
        new_data={"date": str(holiday.date), "name": holiday.name}
    )
    return holiday


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
    holiday = holiday_repository.get_by_id(db, id)
    if holiday:
        old_data = {"date": str(holiday.date), "name": holiday.name}
        holiday_repository.delete(db, id)
        audit_service.log(
            db, actor_id=current_user.id, action="DELETE", entity="HOLIDAY", entity_id=id,
            old_data=old_data
        )
    return {"status": "success"}
