import os
from typing import Any, List

from fastapi import APIRouter, Depends, Body, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.domain.models.user import User
from app.domain.models.enums import UserRole
from app.repositories.adjustment_repository import adjustment_repository
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestUpdate, AdjustmentRequestResponse, \
    AdjustmentAttachmentResponse, AdjustmentWaiverCreate
from app.services.adjustment_service import adjustment_service

router = APIRouter()


@router.post("/", response_model=AdjustmentRequestResponse)
def create_adjustment_request(
        request_in: AdjustmentRequestCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return adjustment_service.create_adjustment_request(db, current_user.id, request_in)


@router.post("/admin/waive", response_model=AdjustmentRequestResponse)
def waive_absence_admin(
        waiver_in: AdjustmentWaiverCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.create_manager_waiver(db, waiver_in, current_user.id)


# -------------------------------------
# ANEXOS E ARQUIVOS
# -------------------------------------

@router.post("/{id}/attachments", response_model=AdjustmentAttachmentResponse)
def upload_adjustment_attachment(
        id: int,
        file: UploadFile = File(...),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return adjustment_service.upload_attachment(db, id, file, current_user.id)


@router.get("/{id}/download", response_class=FileResponse)
def download_adjustment_attachment(
        id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Endpoint para baixar o anexo de um ajuste.
    """
    adjustment = adjustment_repository.get(db, id=id)
    if not adjustment:
        raise HTTPException(status_code=404, detail="Ajuste não encontrado")

    is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
    if adjustment.user_id != current_user.id and not is_manager:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este arquivo")

    if not adjustment.attachments:
        raise HTTPException(status_code=404, detail="Nenhum anexo associado a este ajuste")

    attachment = adjustment.attachments[-1]
    
    # Lógica Robusta:
    # Ignora o caminho completo salvo no banco (que pode ser de outro ambiente/Windows)
    # e reconstrói o caminho usando a configuração atual do servidor (Docker/Linux).
    filename = os.path.basename(attachment.file_path)
    safe_file_path = os.path.join(settings.UPLOAD_DIR, filename)

    if not os.path.exists(safe_file_path):
        # Tenta fallback para o caminho original se o reconstruído falhar
        if os.path.exists(attachment.file_path):
            safe_file_path = attachment.file_path
        else:
            print(f"ERRO DE ARQUIVO: Esperado em {safe_file_path}, DB diz {attachment.file_path}")
            raise HTTPException(status_code=404, detail="Arquivo físico não encontrado no servidor")

    return FileResponse(
        path=safe_file_path, 
        filename=filename,
        media_type='application/octet-stream'
    )


# -------------------------------------

@router.get("/my", response_model=List[AdjustmentRequestResponse])
def read_my_adjustments(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return adjustment_repository.get_all_by_user(db, current_user.id, skip, limit)


@router.get("/", response_model=List[AdjustmentRequestResponse])
def read_all_adjustments(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_repository.get_all(db, skip, limit)


@router.put("/{id}/approve", response_model=AdjustmentRequestResponse)
def approve_adjustment(
        id: int,
        comment: str = Body(None, embed=True),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.approve_adjustment(db, id, current_user.id)


@router.put("/{id}/reject", response_model=AdjustmentRequestResponse)
def reject_adjustment(
        id: int,
        comment: str = Body(..., embed=True),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.reject_adjustment(db, id, current_user.id, comment)


@router.put("/{id}/edit", response_model=AdjustmentRequestResponse)
def edit_adjustment_request(
        id: int,
        request_in: AdjustmentRequestUpdate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.update_adjustment(db, id, request_in, current_user.id)
    
@router.delete("/{id}")
def delete_adjustment(
        id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    adjustment_service.delete_adjustment(db, id, current_user.id)
    return {"status": "success"}
