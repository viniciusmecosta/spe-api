from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.enums import AdjustmentStatus
from app.domain.models.user import User
from app.schemas.adjustment import (
    AdjustmentAttachmentResponse,
    AdjustmentRequestCreate,
    AdjustmentRequestResponse,
    AdjustmentWaiverCreate,
    BulkReprocessExtraTimeRequest,
)
from app.services.adjustment_service import adjustment_service

router = APIRouter()


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Período fechado ou limite de solicitações excedido"},
        401: {"description": "Não autenticado"},
    },
)
def create_adjustment_request(
    request_in: AdjustmentRequestCreate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> AdjustmentRequestResponse:
    return adjustment_service.create_adjustment_request(db, current_user.id, request_in)


@router.post(
    "/admin/waive",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Período fechado ou limite de horas excedido"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def waive_absence_admin(
    waiver_in: AdjustmentWaiverCreate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> AdjustmentRequestResponse:
    return adjustment_service.create_manager_waiver(db, waiver_in, current_user.id)


@router.post(
    "/admin/reprocess-extra-time",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Período fechado ou dados inválidos"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente (somente MAINTAINER)"},
    },
)
def reprocess_historical_extra_time(
    request_in: BulkReprocessExtraTimeRequest,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> dict[str, str]:
    return adjustment_service.reprocess_historical_extra_time(db, request_in, current_user)


@router.post(
    "/{id}/attachments",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Formato de arquivo inválido ou erro no upload"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Solicitação não encontrada"},
    },
)
def upload_adjustment_attachment(
    id: int,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> AdjustmentAttachmentResponse:
    return adjustment_service.upload_attachment(db, id, file, current_user.id)


@router.get(
    "/{id}/download",
    response_class=FileResponse,
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Sem permissão para acessar este arquivo"},
        404: {"description": "Ajuste ou anexo não encontrado"},
    },
)
def download_adjustment_attachment(
    id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> FileResponse:
    safe_file_path, filename = adjustment_service.get_attachment_file_path(
        db, id, current_user
    )
    return FileResponse(
        path=safe_file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get(
    "/my",
    responses={
        401: {"description": "Não autenticado"},
    },
)
def read_my_adjustments(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000),
    status: str | None = Query(
        None, pattern="^(?i)(PENDING|APPROVED|REJECTED|NOT_PENDING)$"
    ),
    order_by: str = Query("created_at", pattern="^(created_at|target_date)$"),
    order_direction: str = Query("desc", pattern="^(asc|desc)$"),
) -> list[AdjustmentRequestResponse]:
    return adjustment_service.get_my_enriched(
        db, current_user.id, skip, limit, month, year, status, order_by, order_direction
    )


@router.get(
    "/",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def read_all_adjustments(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000),
    status: str | None = Query(
        None, pattern="^(?i)(PENDING|APPROVED|REJECTED|NOT_PENDING)$"
    ),
    order_by: str = Query("created_at", pattern="^(created_at|target_date)$"),
    order_direction: str = Query("desc", pattern="^(asc|desc)$"),
) -> list[AdjustmentRequestResponse]:
    return adjustment_service.get_all_enriched(
        db, skip, limit, month, year, status, order_by, order_direction
    )


@router.put(
    "/{id}/approve",
    responses={
        400: {"description": "Período fechado ou solicitação já processada"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Solicitação não encontrada"},
    },
)
def approve_adjustment(
    id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
    comment: Annotated[str | None, Body(embed=True)] = None,
) -> AdjustmentRequestResponse:
    return adjustment_service.approve_adjustment(db, id, current_user.id, comment)


@router.put(
    "/{id}/reject",
    responses={
        400: {"description": "Período fechado ou solicitação já processada"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Solicitação não encontrada"},
    },
)
def reject_adjustment(
    id: int,
    comment: Annotated[str, Body(..., embed=True)],
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> AdjustmentRequestResponse:
    return adjustment_service.reject_adjustment(db, id, current_user.id, comment)


@router.delete(
    "/{id}",
    responses={
        400: {"description": "Período fechado ou solicitação já decidida"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Solicitação não encontrada"},
    },
)
def delete_adjustment(
    id: int,
    reason: Annotated[str, Query(..., min_length=5, description="Justificativa para a exclusão")],
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> dict[str, str]:
    adjustment_service.delete_adjustment(db, id, current_user.id, reason)
    return {"status": "success"}


@router.delete(
    "/admin/{id}",
    responses={
        400: {"description": "Período fechado"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente (somente MAINTAINER)"},
        404: {"description": "Solicitação não encontrada"},
    },
)
def admin_delete_adjustment(
    id: int,
    reason: Annotated[str, Query(..., min_length=5, description="Justificativa para a exclusão")],
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    adjustment_service.admin_delete_adjustment(db, id, current_user.id, reason)
    return {"status": "success"}


@router.put(
    "/admin/{id}/revert-status",
    responses={
        400: {"description": "Período fechado"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente (somente MAINTAINER)"},
        404: {"description": "Solicitação não encontrada"},
    },
)
def admin_revert_adjustment_status(
    id: int,
    status: Annotated[AdjustmentStatus, Body(..., embed=True)],
    comment: Annotated[str, Body(..., embed=True)],
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> AdjustmentRequestResponse:
    return adjustment_service.revert_adjustment_status(
        db, id, current_user.id, status, comment
    )
