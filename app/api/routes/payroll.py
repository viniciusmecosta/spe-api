from typing import Any, List

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.payroll import PayrollClosureCreate, PayrollClosureResponse
from app.services.payroll_service import payroll_service
from app.services.email_service import dispatch_payroll_email

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
        background_tasks: BackgroundTasks,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    closure = payroll_service.close_period(db, period.month, period.year, current_user)
    
    background_tasks.add_task(
        dispatch_payroll_email, 
        "Fechamento", current_user.name, current_user.email, period.month, period.year, current_user.id
    )
    
    return closure


@router.post("/reopen", response_model=dict)
def reopen_payroll_period(
        period: PayrollClosureCreate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    result = payroll_service.reopen_period(db, period.month, period.year, current_user)
    
    background_tasks.add_task(
        dispatch_payroll_email, 
        "Reabertura", current_user.name, current_user.email, period.month, period.year, current_user.id
    )
    
    return result
