from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
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


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def list_payroll_periods(
    year: int,
    db: Annotated[Session, Depends(deps.get_db)],
) -> list[PayrollClosureResponse]:
    return payroll_service.list_periods(db, year)


@router.post(
    "/close",
    responses={
        400: {"description": "Período já fechado ou inválido"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def close_payroll_period(
    period: PayrollClosureCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> PayrollClosureResponse:
    return payroll_service.close_period(db, period.month, period.year, current_user, background_tasks)


@router.post(
    "/reopen",
    responses={
        400: {"description": "Período não está fechado ou dados inválidos"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def reopen_payroll_period(
    period: PayrollReopenCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> SuccessResponse:
    return payroll_service.reopen_period(
        db, period.month, period.year, period.observation, current_user, background_tasks
    )


@router.post(
    "/{closure_id}/legacy-report",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={
        400: {"description": "Arquivo inválido ou erro no upload"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Fechamento não encontrado"},
    },
)
def upload_legacy_report(
    closure_id: int,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(deps.get_db)],
) -> SuccessResponse:
    payroll_service.upload_legacy_report(db, closure_id, file.filename, file.file.read())
    return SuccessResponse(status="success", message="Documento legado anexado com sucesso.")
