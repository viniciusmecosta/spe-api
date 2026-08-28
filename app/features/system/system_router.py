from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)

from app.features.system.audit_service import AuditService
from app.features.system.routine_log_service import RoutineLogService
from app.features.system.routine_orchestrator import RoutineOrchestrator
from app.features.system.system_schemas import (
    AuditLogResponse,
    RoutineLogResponse,
)
from app.features.system.telegram_service import TelegramService
from app.features.users.user_models import User
from app.shared import deps
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    FORBIDDEN_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

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
        skip: int = 0,
        limit: int = 100,
) -> list[AuditLogResponse]:
    return await service.get_logs(
        action=action,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit,
    )


@backup_router.post(
    "/trigger",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**BAD_REQUEST_RESPONSE},
)
async def trigger_manual_backup(
        audit_svc: Annotated[AuditService, Depends()],
        routine_orch: Annotated[RoutineOrchestrator, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    sent = await routine_orch.send_manual_backup_email()
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falha ao gerar ou enviar o backup.",
        )
    audit_svc.log(user_id=current_user.id, action="MANUAL_BACKUP_EMAIL", entity="SYSTEM", entity_id=0)
    return {"status": "success", "message": "Backup gerado e enviado com sucesso."}


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
        skip: int = 0,
        limit: int = 100,
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


@telegram_actions_router.post(
    "/manual-backup",
    dependencies=[Depends(deps.get_current_maintainer)],
)
async def trigger_manual_backup_telegram(
        background_tasks: BackgroundTasks,
        audit_svc: Annotated[AuditService, Depends()],
        routine_orch: Annotated[RoutineOrchestrator, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    background_tasks.add_task(routine_orch.execute_manual_backup_telegram)
    audit_svc.log(user_id=current_user.id, action="MANUAL_BACKUP_TELEGRAM", entity="SYSTEM", entity_id=0)
    return {"message": "Backup manual enviado para a fila de processamento do Telegram."}


@telegram_actions_router.post(
    "/manual-report",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**BAD_REQUEST_RESPONSE},
)
async def trigger_manual_report_telegram(
        background_tasks: BackgroundTasks,
        start_date: Annotated[date, Query(description="Data inicial do período (YYYY-MM-DD)")],
        end_date: Annotated[date, Query(description="Data final do período (YYYY-MM-DD)")],
        audit_svc: Annotated[AuditService, Depends()],
        telegram_svc: Annotated[TelegramService, Depends()],
        routine_orch: Annotated[RoutineOrchestrator, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    telegram_svc.validate_manual_report_dates(start_date, end_date)
    background_tasks.add_task(routine_orch.send_manual_report_telegram, start_date, end_date)
    audit_svc.log(user_id=current_user.id, action="MANUAL_REPORT_TELEGRAM", entity="SYSTEM", entity_id=0,
                  new_data={"start_date": str(start_date), "end_date": str(end_date)})
    return {
        "message": f"Relatório do período {start_date} até {end_date} enviado para processamento em background."
    }

