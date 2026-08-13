from typing import Any

from app.api import deps
from app.domain.models.user import User
from app.schemas.payroll import (
    PayrollClosureCreate,
    PayrollClosureResponse,
    PayrollReopenCreate,
)
from app.schemas.time_record import SuccessResponse
from app.services.payroll_service import payroll_service
from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.orm import Session

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

@router.post("/{closure_id}/legacy-report", response_model=SuccessResponse)
def upload_legacy_report(
        closure_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
) -> Any:
    payroll_service.upload_legacy_report(db, closure_id, file.filename, file.file.read())
    return {"status": "success", "message": "Documento legado anexado com sucesso."}
