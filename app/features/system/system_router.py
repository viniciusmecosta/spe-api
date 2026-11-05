from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from app.features.system.audit_service import AuditService
from app.features.system.job_schemas import (
    JobDetailResponse,
    JobRetryResponse,
)
from app.features.system.job_service import JobService
from app.features.system.routine_log_service import RoutineLogService
from app.features.system.system_schemas import (
    AuditLogResponse,
    RoutineLogResponse,
)
from app.shared import deps
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    FORBIDDEN_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from app.shared.validation import PageLimit, PageOffset

audit_router = APIRouter(responses={**AUTH_RESPONSES})
backup_router = APIRouter(responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE})
routine_logs_router = APIRouter(responses={**AUTH_RESPONSES})
telegram_actions_router = APIRouter(responses={**AUTH_RESPONSES})


@audit_router.get(
    "/",
    dependencies=[Depends(deps.get_current_manager)],
)
async def read_audit_logs(
        service: Annotated[AuditService, Depends()],
        action: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
        skip: PageOffset = 0,
        limit: PageLimit = 100,
) -> list[AuditLogResponse]:
    return await service.get_logs(
        action=action,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit,
    )


@routine_logs_router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
)
async def read_routine_logs(
        service: Annotated[RoutineLogService, Depends()],
        routine_type: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
        skip: PageOffset = 0,
        limit: PageLimit = 100,
) -> list[RoutineLogResponse]:
    return await service.get_logs(
        routine_type=routine_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit,
    )


@routine_logs_router.get('/jobs/{job_id}', response_model=JobDetailResponse,
                         dependencies=[Depends(deps.get_current_maintainer)])
async def get_job(job_id: int, service: Annotated[JobService, Depends()]):
    return await service.get(job_id)


@routine_logs_router.post('/jobs/{job_id}/retry', response_model=JobRetryResponse,
                          dependencies=[Depends(deps.get_current_maintainer)])
async def retry_job(job_id: int, service: Annotated[JobService, Depends()]):
    return await service.retry(job_id)


