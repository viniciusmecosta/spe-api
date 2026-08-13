from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.api.deps import get_current_maintainer
from app.services.routine_orchestrator import routine_orchestrator

router = APIRouter()


@router.post(
    "/manual-backup",
    dependencies=[Depends(get_current_maintainer)],
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def trigger_manual_backup(
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    background_tasks.add_task(routine_orchestrator.execute_manual_backup_telegram)
    return {"message": "Backup manual enviado para a fila de processamento do Telegram."}


@router.post(
    "/manual-report",
    dependencies=[Depends(get_current_maintainer)],
    responses={
        400: {"description": "A data de início não pode ser maior que a data de fim ou período excedido."},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        422: {"description": "Erro de validação de data"},
    },
)
def trigger_manual_report(
    background_tasks: BackgroundTasks,
    start_date: date = Query(..., description="Data inicial do período (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Data final do período (YYYY-MM-DD)"),
) -> dict[str, str]:
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="A data de início não pode ser maior que a data de fim.",
        )

    delta_days = (end_date - start_date).days
    if delta_days > 7:
        raise HTTPException(
            status_code=400,
            detail="Período excedido. O relatório gerencial no Telegram é limitado a no máximo 7 dias. Utilize a plataforma web para consultar períodos mais extensos.",
        )

    background_tasks.add_task(routine_orchestrator.send_manual_report_telegram, start_date, end_date)
    return {
        "message": f"Relatório do período {start_date} até {end_date} enviado para processamento em background."
    }
