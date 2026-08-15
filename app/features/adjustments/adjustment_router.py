from typing import Annotated

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

from app.shared.enums import AdjustmentStatus
from app.features.users.user_models import User
from app.features.adjustments.adjustment_schemas import (
    AdjustmentAttachmentResponse,
    AdjustmentRequestCreate,
    AdjustmentRequestResponse,
    AdjustmentWaiverCreate,
    BulkReprocessExtraTimeRequest,
)
from app.features.adjustments.adjustment_service import adjustment_service
from app.shared import deps
from app.shared.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE},
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
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
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
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
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
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
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
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
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


@router.get("/my")
def read_my_adjustments(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    year: Annotated[int | None, Query(ge=2000)] = None,
    status: Annotated[
        str | None,
        Query(pattern="^(?i)(PENDING|APPROVED|REJECTED|NOT_PENDING)$"),
    ] = None,
    order_by: Annotated[str, Query(pattern="^(created_at|target_date)$")] = "created_at",
    order_direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> list[AdjustmentRequestResponse]:
    return adjustment_service.get_my_enriched(
        db, current_user.id, skip, limit, month, year, status, order_by, order_direction
    )


@router.get(
    "/",
    responses={**FORBIDDEN_RESPONSE},
)
def read_all_adjustments(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    year: Annotated[int | None, Query(ge=2000)] = None,
    status: Annotated[
        str | None,
        Query(pattern="^(?i)(PENDING|APPROVED|REJECTED|NOT_PENDING)$"),
    ] = None,
    order_by: Annotated[str, Query(pattern="^(created_at|target_date)$")] = "created_at",
    order_direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> list[AdjustmentRequestResponse]:
    return adjustment_service.get_all_enriched(
        db, skip, limit, month, year, status, order_by, order_direction
    )


@router.put(
    "/{id}/approve",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
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
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
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
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
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
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
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
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
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
