from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any, List

from app.api import deps
from app.domain.models.user import User
from app.schemas.payroll import PayrollClosureCreate, PayrollClosureResponse
from app.services.payroll_service import payroll_service

router = APIRouter()


@router.get("/", response_model=List[PayrollClosureResponse])
def list_payroll_periods(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return payroll_service.list_periods(db)


@router.post("/close", response_model=PayrollClosureResponse)
def close_payroll_period(
        period: PayrollClosureCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return payroll_service.close_period(db, period.month, period.year, current_user)


@router.post("/reopen", response_model=dict)
def reopen_payroll_period(
        period: PayrollClosureCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return payroll_service.reopen_period(db, period.month, period.year, current_user)