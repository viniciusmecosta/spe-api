from typing import Annotated

from fastapi import APIRouter, Depends

from app.features.system.audit_service import AuditService
from app.features.system.job_schemas import (
    JobAdmissionResponse,
    OperationJobRequest,
    OperationsResponse,
    ReadinessResponse,
)
from app.features.system.operations_service import OperationsService
from app.features.system.routine_orchestrator import RoutineOrchestrator
from app.features.system.telegram_service import TelegramService
from app.features.users.user_models import User
from app.shared import deps
from app.shared.openapi_responses import AUTH_RESPONSES, BAD_REQUEST_RESPONSE

router = APIRouter()


@router.get('/ready', tags=['Health'], response_model=ReadinessResponse)
async def readiness(service: Annotated[OperationsService, Depends()]):
    return await service.readiness()


@router.get('/operations', dependencies=[Depends(deps.get_current_maintainer)], tags=['Health'],
            response_model=OperationsResponse)
async def operations(service: Annotated[OperationsService, Depends()]):
    return await service.snapshot()


@router.post(
    "/operations/jobs", status_code=202, tags=["Operations"],
    response_model=JobAdmissionResponse, response_model_exclude_unset=True,
    responses={**AUTH_RESPONSES, **BAD_REQUEST_RESPONSE},
)
async def submit_operation_job(
    operation: OperationJobRequest,
    routine_orch: Annotated[RoutineOrchestrator, Depends()],
    audit_svc: Annotated[AuditService, Depends()],
    telegram_svc: Annotated[TelegramService, Depends()],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    return await routine_orch.submit_manual_job(
        operation=operation, current_user=current_user,
        audit_svc=audit_svc, telegram_svc=telegram_svc,
    )
