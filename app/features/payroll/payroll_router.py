from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.features.users.user_models import User
from app.features.payroll.payroll_schemas import (
    PayrollClosureCreate,
    PayrollClosureResponse,
    PayrollReopenCreate,
)
from app.features.payroll.payroll_service import payroll_service
from app.features.time_records.time_record_schemas import SuccessResponse
from app.shared import deps
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
)

router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
)
def list_payroll_periods(
    year: int,
    db: Annotated[Session, Depends(deps.get_db)],
) -> list[PayrollClosureResponse]:
    return payroll_service.list_periods(db, year)


@router.post(
    "/close",
    responses={**BAD_REQUEST_RESPONSE},
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
    responses={**BAD_REQUEST_RESPONSE},
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
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def upload_legacy_report(
    closure_id: int,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(deps.get_db)],
) -> SuccessResponse:
    payroll_service.upload_legacy_report(db, closure_id, file.filename or "", file.file.read())
    return SuccessResponse(status="success", message="Documento legado anexado com sucesso.")
