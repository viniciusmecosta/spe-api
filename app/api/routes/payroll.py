from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any

from app.api import deps
from app.domain.models.user import User
from app.schemas.payroll import PayrollClosureCreate, PayrollClosureResponse
from app.services.payroll_service import payroll_service

router = APIRouter()


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
        current_user: User = Depends(deps.get_current_active_user)  # Service valida se é MAINTAINER
) -> Any:
    return payroll_service.reopen_period(db, period.month, period.year, current_user)
