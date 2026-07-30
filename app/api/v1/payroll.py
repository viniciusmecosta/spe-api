from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
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


import os
from fastapi import UploadFile, File, HTTPException
from app.core.config import settings
from app.domain.models.payroll import PayrollClosure


@router.post("/{closure_id}/legacy-report", response_model=SuccessResponse)
def upload_legacy_report(
        closure_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
) -> Any:
    closure = db.query(PayrollClosure).get(closure_id)
    if not closure:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")

    legacy_dir = os.path.join(settings.UPLOAD_DIR, "reports", "legacy")
    os.makedirs(legacy_dir, exist_ok=True)

    filename = f"legacy_{closure_id}_{file.filename}"
    file_path = os.path.join(legacy_dir, filename)

    with open(file_path, "wb") as f:
        f.write(file.file.read())

    closure.report_path = f"reports/legacy/{filename}"
    db.commit()

    return {"status": "success", "message": "Documento legado anexado com sucesso."}
