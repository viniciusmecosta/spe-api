from typing import Any

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.repositories.holiday_repository import holiday_repository
from app.schemas.holiday import HolidayCreate, HolidayResponse
from app.services.audit_service import audit_service
from app.services.payroll_service import payroll_service

router = APIRouter()


@router.post("/", response_model=HolidayResponse, status_code=status.HTTP_201_CREATED)
def create_holiday(
        holiday_in: HolidayCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    payroll_service.validate_period_open(db, holiday_in.date)
    if holiday_repository.get_by_date(db, holiday_in.date):
        raise HTTPException(status_code=400, detail="Já existe um feriado cadastrado para esta data.")
        
    holiday = holiday_repository.create(db, holiday_in)
    audit_service.log(
        db, user_id=current_user.id, action="CREATE", entity="HOLIDAY", entity_id=holiday.id,
        new_data={"date": str(holiday.date), "name": holiday.name}
    )
    return holiday


@router.get("/", response_model=list[HolidayResponse])
def read_holidays(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return holiday_repository.get_all(db)


@router.delete("/{id}", response_model=dict)
def delete_holiday(
        id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    holiday = holiday_repository.get_by_id(db, id)
    if holiday:
        payroll_service.validate_period_open(db, holiday.date)
        old_data = {"date": str(holiday.date), "name": holiday.name}
        holiday_repository.delete(db, id)
        audit_service.log(
            db, user_id=current_user.id, action="DELETE", entity="HOLIDAY", entity_id=id,
            old_data=old_data
        )
    return {"status": "success"}
