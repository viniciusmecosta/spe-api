from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.deps import get_current_maintainer
from app.api.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
)
from app.services.routine_orchestrator import routine_orchestrator
from app.services.telegram_service import telegram_service

router = APIRouter(responses={**AUTH_RESPONSES})


@router.post(
    "/manual-backup",
    dependencies=[Depends(get_current_maintainer)],
)
def trigger_manual_backup(
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    background_tasks.add_task(routine_orchestrator.execute_manual_backup_telegram)
    return {"message": "Backup manual enviado para a fila de processamento do Telegram."}


@router.post(
    "/manual-report",
    dependencies=[Depends(get_current_maintainer)],
    responses={**BAD_REQUEST_RESPONSE},
)
def trigger_manual_report(
    background_tasks: BackgroundTasks,
    start_date: date = Query(..., description="Data inicial do período (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Data final do período (YYYY-MM-DD)"),
) -> dict[str, str]:
    telegram_service.validate_manual_report_dates(start_date, end_date)
    background_tasks.add_task(routine_orchestrator.send_manual_report_telegram, start_date, end_date)
    return {
        "message": f"Relatório do período {start_date} até {end_date} enviado para processamento em background."
    }
