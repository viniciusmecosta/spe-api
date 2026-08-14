from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.api.openapi_responses import BAD_REQUEST_RESPONSE, FORBIDDEN_RESPONSE, UNAUTHORIZED_RESPONSE
from app.services.routine_orchestrator import routine_orchestrator

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE})


@router.post(
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
