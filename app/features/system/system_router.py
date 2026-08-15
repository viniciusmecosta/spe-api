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
from sqlalchemy.orm import Session

from app.features.system.audit_service import audit_service
from app.features.system.routine_log_service import routine_log_service
from app.features.system.routine_orchestrator import routine_orchestrator
from app.features.system.system_schemas import (
    AuditLogResponse,
    RoutineLogResponse,
)
from app.features.system.telegram_service import telegram_service
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


# --- Audit Logs endpoints ---
@audit_router.get(
    "/",
    dependencies=[Depends(deps.get_current_manager)],
)
def read_audit_logs(
        db: Annotated[Session, Depends(deps.get_db)],
        action: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
        skip: int = 0,
        limit: int = 100,
) -> list[AuditLogResponse]:
    return audit_service.get_logs(
        db,
        action=action,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit,
    )


# --- Backup endpoints ---
@backup_router.post(
    "/trigger",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**BAD_REQUEST_RESPONSE},
)
def trigger_manual_backup(
        db: Annotated[Session, Depends(deps.get_db)],
) -> dict[str, str]:
    sent = routine_orchestrator.send_manual_backup_email(db)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falha ao gerar ou enviar o backup.",
        )
    return {"status": "success", "message": "Backup gerado e enviado com sucesso."}


# --- Routine Logs endpoints ---
@routine_logs_router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
)
def read_routine_logs(
        db: Annotated[Session, Depends(deps.get_db)],
        routine_type: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
        skip: int = 0,
        limit: int = 100,
) -> list[RoutineLogResponse]:
    return routine_log_service.get_logs(
        db,
        routine_type=routine_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit,
    )


# --- Telegram Actions endpoints ---
@telegram_actions_router.post(
    "/manual-backup",
    dependencies=[Depends(deps.get_current_maintainer)],
)
def trigger_manual_backup_telegram(
        background_tasks: BackgroundTasks,
) -> dict[str, str]:
    background_tasks.add_task(routine_orchestrator.execute_manual_backup_telegram)
    return {"message": "Backup manual enviado para a fila de processamento do Telegram."}


@telegram_actions_router.post(
    "/manual-report",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**BAD_REQUEST_RESPONSE},
)
def trigger_manual_report_telegram(
        background_tasks: BackgroundTasks,
        start_date: Annotated[date, Query(description="Data inicial do período (YYYY-MM-DD)")],
        end_date: Annotated[date, Query(description="Data final do período (YYYY-MM-DD)")],
) -> dict[str, str]:
    telegram_service.validate_manual_report_dates(start_date, end_date)
    background_tasks.add_task(routine_orchestrator.send_manual_report_telegram, start_date, end_date)
    return {
        "message": f"Relatório do período {start_date} até {end_date} enviado para processamento em background."
    }
