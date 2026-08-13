from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.services.routine_orchestrator import routine_orchestrator

router = APIRouter()


@router.post(
    "/trigger",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={
        400: {"description": "Falha ao gerar ou enviar o backup."},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
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
