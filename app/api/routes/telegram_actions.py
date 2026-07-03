from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.api.deps import get_current_maintainer
from app.domain.models.user import User
from app.services.routine_orchestrator import routine_orchestrator

router = APIRouter()


@router.post("/manual-backup")
def trigger_manual_backup(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_maintainer)
):
    background_tasks.add_task(routine_orchestrator.execute_manual_backup_telegram)
    return {"message": "Backup manual enviado para a fila de processamento do Telegram."}


@router.post("/manual-report")
def trigger_manual_report(
        background_tasks: BackgroundTasks,
        start_date: date = Query(..., description="Data inicial do período (YYYY-MM-DD)"),
        end_date: date = Query(..., description="Data final do período (YYYY-MM-DD)"),
        current_user: User = Depends(get_current_maintainer)
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="A data de início não pode ser maior que a data de fim."
        )

    delta_days = (end_date - start_date).days
    if delta_days > 7:
        raise HTTPException(
            status_code=400,
            detail="Período excedido. O relatório gerencial no Telegram é limitado a no máximo 7 dias. Utilize a plataforma web para consultar períodos mais extensos."
        )

    background_tasks.add_task(routine_orchestrator.send_manual_report_telegram, start_date, end_date)
    return {
        "message": f"Relatório do período {start_date} até {end_date} enviado para processamento em background."
    }
