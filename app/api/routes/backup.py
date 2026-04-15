from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.services.audit_service import audit_service
from app.services.backup_service import backup_service

router = APIRouter()


@router.post("/trigger", response_model=dict)
def trigger_manual_backup(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    sent = backup_service.send_database_backup(db)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao gerar ou enviar o backup."
        )

    audit_service.log(
        db=db,
        actor_id=current_user.id,
        actor_name=current_user.name,
        action="MANUAL_BACKUP",
        entity="SYSTEM",
        new_data={"status": "success"}
    )

    return {"status": "success", "message": "Backup gerado e enviado com sucesso."}
