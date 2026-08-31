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

from app.features.adjustments.adjustment_schemas import (
    AdjustmentAttachmentResponse,
    AdjustmentRequestCreate,
    AdjustmentRequestResponse,
    AdjustmentWaiverCreate,
    BulkReprocessExtraTimeRequest,
)
from app.features.adjustments.adjustment_service import AdjustmentService
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import AdjustmentStatus
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
async def create_adjustment_request(
        request_in: AdjustmentRequestCreate,
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> AdjustmentRequestResponse:
    return await service.create_adjustment_request(user_id=current_user.id, obj_in=request_in)


@router.post(
    "/admin/waive",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def waive_absence_admin(
        waiver_in: AdjustmentWaiverCreate,
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> AdjustmentRequestResponse:
    return await service.create_manager_waiver(waiver_in=waiver_in, manager_id=current_user.id)


@router.post(
    "/admin/reprocess-extra-time",
    status_code=status.HTTP_200_OK,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def reprocess_historical_extra_time(
        request_in: BulkReprocessExtraTimeRequest,
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> dict[str, str]:
    return await service.reprocess_historical_extra_time(request_in=request_in, current_user=current_user)


@router.post(
    "/{id}/attachments",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def upload_adjustment_attachment(
        id: int,
        file: Annotated[UploadFile, File(...)],
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> AdjustmentAttachmentResponse:
    return await service.upload_attachment(request_id=id, file=file, user_id=current_user.id)


@router.get(
    "/{id}/download",
    response_class=FileResponse,
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def download_adjustment_attachment(
        id: int,
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> FileResponse:
    safe_file_path, filename = await service.get_attachment_file_path(
        adjustment_id=id, current_user=current_user
    )
    return FileResponse(
        path=safe_file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/my")
async def read_my_adjustments(
        service: Annotated[AdjustmentService, Depends()],
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
    return await service.get_my_enriched(
        user_id=current_user.id, skip=skip, limit=limit, month=month, year=year, status=status, order_by=order_by, order_direction=order_direction
    )


@router.get(
    "/",
    responses={**FORBIDDEN_RESPONSE},
)
async def read_all_adjustments(
        service: Annotated[AdjustmentService, Depends()],
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
    return await service.get_all_enriched(
        skip=skip, limit=limit, month=month, year=year, status=status, order_by=order_by, order_direction=order_direction
    )


@router.put(
    "/{id}/approve",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def approve_adjustment(
        id: int,
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
        comment: Annotated[str | None, Body(embed=True)] = None,
) -> AdjustmentRequestResponse:
    return await service.approve_adjustment(request_id=id, manager_id=current_user.id, comment=comment)


@router.put(
    "/{id}/reject",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def reject_adjustment(
        id: int,
        comment: Annotated[str, Body(..., embed=True)],
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> AdjustmentRequestResponse:
    return await service.reject_adjustment(request_id=id, manager_id=current_user.id, comment=comment)


@router.delete(
    "/{id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def delete_adjustment(
        id: int,
        reason: Annotated[str, Query(..., min_length=5, description="Justificativa para a exclusão")],
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> dict[str, str]:
    await service.delete_adjustment(adjustment_id=id, manager_id=current_user.id, reason=reason)
    return {"status": "success"}


@router.delete(
    "/admin/{id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def admin_delete_adjustment(
        id: int,
        reason: Annotated[str, Query(..., min_length=5, description="Justificativa para a exclusão")],
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    await service.admin_delete_adjustment(adjustment_id=id, admin_id=current_user.id, reason=reason)
    return {"status": "success"}


@router.put(
    "/admin/{id}/revert-status",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def admin_revert_adjustment_status(
        id: int,
        status: Annotated[AdjustmentStatus, Body(..., embed=True)],
        comment: Annotated[str, Body(..., embed=True)],
        service: Annotated[AdjustmentService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> AdjustmentRequestResponse:
    return await service.revert_adjustment_status(
        request_id=id, manager_id=current_user.id, new_status=status, comment=comment
    )
