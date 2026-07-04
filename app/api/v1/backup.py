from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.services.routine_orchestrator import routine_orchestrator

router = APIRouter()


@router.post("/trigger", response_model=dict)
def trigger_manual_backup(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    sent = routine_orchestrator.send_manual_backup_email(db)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao gerar ou enviar o backup."
        )

    return {"status": "success", "message": "Backup gerado e enviado com sucesso."}
