from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile

from app.features.payroll.payroll_schemas import (
    PayrollClosureCreate,
    PayrollClosureResponse,
    PayrollReopenCreate,
)
from app.features.payroll.payroll_service import PayrollService
from app.features.time_records.time_record_schemas import SuccessResponse
from app.features.users.user_models import User
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
async def list_payroll_periods(
        year: int,
        service: Annotated[PayrollService, Depends()],
) -> list[PayrollClosureResponse]:
    return await service.list_periods(year=year)


@router.post(
    "/close",
    responses={**BAD_REQUEST_RESPONSE},
)
async def close_payroll_period(
        period: PayrollClosureCreate,
        background_tasks: BackgroundTasks,
        service: Annotated[PayrollService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> PayrollClosureResponse:
    return await service.close_period(month=period.month, year=period.year, current_user=current_user,
                                      background_tasks=background_tasks)


@router.post(
    "/reopen",
    responses={**BAD_REQUEST_RESPONSE},
)
async def reopen_payroll_period(
        period: PayrollReopenCreate,
        background_tasks: BackgroundTasks,
        service: Annotated[PayrollService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> SuccessResponse:
    return await service.reopen_period(
        month=period.month, year=period.year, observation=period.observation, current_user=current_user, background_tasks=background_tasks
    )


@router.post(
    "/{closure_id}/legacy-report",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def upload_legacy_report(
        closure_id: int,
        file: Annotated[UploadFile, File(...)],
        service: Annotated[PayrollService, Depends()],
) -> SuccessResponse:
    await service.upload_legacy_report(closure_id=closure_id, original_filename=file.filename or "",
                                       file_content=file.file.read())
    return SuccessResponse(status="success", message="Documento legado anexado com sucesso.")
