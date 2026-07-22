import os
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Body, UploadFile, File, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.domain.models.enums import UserRole, AdjustmentStatus
from app.domain.models.user import User
from app.repositories.adjustment_repository import adjustment_repository
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentRequestResponse, \
    AdjustmentAttachmentResponse, AdjustmentWaiverCreate
from app.services.adjustment_service import adjustment_service

router = APIRouter()


@router.post("/", response_model=AdjustmentRequestResponse, status_code=status.HTTP_201_CREATED)
def create_adjustment_request(
        request_in: AdjustmentRequestCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return adjustment_service.create_adjustment_request(db, current_user.id, request_in)


@router.post("/admin/waive", response_model=AdjustmentRequestResponse, status_code=status.HTTP_201_CREATED)
def waive_absence_admin(
        waiver_in: AdjustmentWaiverCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.create_manager_waiver(db, waiver_in, current_user.id)


from app.schemas.adjustment import BulkReprocessExtraTimeRequest
from app.services.tolerance_cron_service import tolerance_cron_service

@router.post("/admin/reprocess-extra-time", status_code=status.HTTP_200_OK)
def reprocess_historical_extra_time(
        request_in: BulkReprocessExtraTimeRequest,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    if current_user.role != UserRole.MAINTAINER:
        raise HTTPException(status_code=403, detail="Apenas MAINTAINER pode executar o reprocessamento em lote")

    from app.services.payroll_service import payroll_service
    from datetime import date
    
    curr = request_in.start_date.replace(day=1)
    while curr <= request_in.end_date:
        payroll_service.validate_period_open(db, curr)
        if curr.month == 12:
            curr = curr.replace(year=curr.year + 1, month=1)
        else:
            curr = curr.replace(month=curr.month + 1)
        
    tolerance_cron_service.reprocess_historical_entries(
        db=db,
        start_date=request_in.start_date,
        end_date=request_in.end_date,
        user_ids=request_in.user_ids
    )
    
    return {"status": "success", "message": "Reprocessamento concluído"}



@router.post("/{id}/attachments", response_model=AdjustmentAttachmentResponse, status_code=status.HTTP_201_CREATED)
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
    adjustment = adjustment_repository.get(db, id=id)
    if not adjustment:
        raise HTTPException(status_code=404, detail="Ajuste não encontrado")

    is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
    if adjustment.user_id != current_user.id and not is_manager:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este arquivo")

    if not adjustment.attachments:
        raise HTTPException(status_code=404, detail="Nenhum anexo associado a este ajuste")

    attachment = adjustment.attachments[-1]
    filename = os.path.basename(attachment.file_path)
    safe_file_path = os.path.join(settings.UPLOAD_DIR, filename)

    if not os.path.exists(safe_file_path):
        if os.path.exists(attachment.file_path):
            safe_file_path = attachment.file_path
        else:
            raise HTTPException(status_code=404, detail="Arquivo físico não encontrado no servidor")

    return FileResponse(
        path=safe_file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


@router.get("/my", response_model=List[AdjustmentRequestResponse])
def read_my_adjustments(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        month: Optional[int] = Query(None, ge=1, le=12),
        year: Optional[int] = Query(None, ge=2000),
        status: Optional[str] = Query(None, pattern="^(?i)(PENDING|APPROVED|REJECTED|NOT_PENDING)$"),
        order_by: str = Query("created_at", pattern="^(created_at|target_date)$"),
        order_direction: str = Query("desc", pattern="^(asc|desc)$"),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return adjustment_service.get_my_enriched(
        db, current_user.id, skip, limit, month, year, status, order_by, order_direction
    )


@router.get("/", response_model=List[AdjustmentRequestResponse])
def read_all_adjustments(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        month: Optional[int] = Query(None, ge=1, le=12),
        year: Optional[int] = Query(None, ge=2000),
        status: Optional[str] = Query(None, pattern="^(?i)(PENDING|APPROVED|REJECTED|NOT_PENDING)$"),
        order_by: str = Query("created_at", pattern="^(created_at|target_date)$"),
        order_direction: str = Query("desc", pattern="^(asc|desc)$"),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.get_all_enriched(
        db, skip, limit, month, year, status, order_by, order_direction
    )


@router.put("/{id}/approve", response_model=AdjustmentRequestResponse)
def approve_adjustment(
        id: int,
        comment: str | None = Body(None, embed=True),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.approve_adjustment(db, id, current_user.id, comment)


@router.put("/{id}/reject", response_model=AdjustmentRequestResponse)
def reject_adjustment(
        id: int,
        comment: str = Body(..., embed=True),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return adjustment_service.reject_adjustment(db, id, current_user.id, comment)



@router.delete("/{id}", response_model=dict)
def delete_adjustment(
        id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    adjustment_service.delete_adjustment(db, id, current_user.id)
    return {"status": "success"}

@router.delete("/admin/{id}", response_model=dict)
def admin_delete_adjustment(
        id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
) -> Any:
    adjustment_service.admin_delete_adjustment(db, id, current_user.id)
    return {"status": "success"}

@router.put("/admin/{id}/revert-status", response_model=AdjustmentRequestResponse)
def admin_revert_adjustment_status(
        id: int,
        status: AdjustmentStatus = Body(..., embed=True),
        comment: str = Body(..., embed=True),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
) -> Any:
    """
    Alterar a decisão de um ajuste já decidido. Exclusivo para mantenedores.
    Reverte automaticamente quaisquer efeitos no TimeRecord.
    """
    return adjustment_service.revert_adjustment_status(db, id, current_user.id, status, comment)
