from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.payroll import (
    PayrollClosureCreate,
    PayrollClosureResponse,
    PayrollReopenCreate,
)
from app.schemas.time_record import SuccessResponse
from app.services.payroll_service import payroll_service

router = APIRouter()


@router.get("/", response_model=list[PayrollClosureResponse])
def list_payroll_periods(
        year: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
) -> Any:
    return payroll_service.list_periods(db, year)


@router.post("/close", response_model=PayrollClosureResponse)
def close_payroll_period(
        period: PayrollClosureCreate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
) -> Any:
    return payroll_service.close_period(db, period.month, period.year, current_user, background_tasks)


@router.post("/reopen", response_model=SuccessResponse)
def reopen_payroll_period(
        period: PayrollReopenCreate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
) -> Any:
    return payroll_service.reopen_period(db, period.month, period.year, period.observation, current_user, background_tasks)
