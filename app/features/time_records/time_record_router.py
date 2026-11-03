from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    Request,
    Response,
    status,
)

from app.features.time_records.time_record_schemas import (
    AdministrativeTimeRecordCreate,
    ManualTimeRecordCreate,
    ReceiptResponse,
    SuccessResponse,
    TimeRecordFilters,
    TimeRecordResponse,
    TimeRecordTimelineResponse,
    TimeRecordUpdate,
)
from app.features.time_records.time_record_service import TimeRecordService
from app.features.users.user_models import User
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
    "", status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def register_manual_record(
    record_in: ManualTimeRecordCreate | AdministrativeTimeRecordCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    service: Annotated[TimeRecordService, Depends()],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    return await service.create_record(
        current_user=current_user, request=request, record_in=record_in,
        background_tasks=background_tasks,
    )


@router.get("", responses={**FORBIDDEN_RESPONSE})
async def list_records(
    filters: Annotated[TimeRecordFilters, Query()],
    service: Annotated[TimeRecordService, Depends()],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> list[TimeRecordResponse]:
    return await service.list_records(filters=filters, current_user=current_user)


@router.post(
    "/{id}/type-transitions",
    responses={**BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def toggle_record_type(
        id: int,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    return await service.toggle_record_type(
        record_id=id, current_user=current_user
    )


@router.patch(
    "/{record_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def update_time_record_admin(
        record_id: int,
        record_in: TimeRecordUpdate,
        request: Request,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> TimeRecordResponse:
    return await service.update_admin_record(
        record_id=record_id, obj_in=record_in, manager_id=current_user.id, request=request
    )


@router.delete(
    "/{record_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def delete_time_record(
        record_id: int,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
        justification: Annotated[str, Query(min_length=5, max_length=300)],
) -> SuccessResponse:
    await service.delete_admin_record(
        record_id=record_id, manager_id=current_user.id,
        justification=justification, validate_justification=True,
    )
    return SuccessResponse(status="success", message="Registro excluído com sucesso.")


@router.get(
    "/{id}/timeline",
    responses={**FORBIDDEN_RESPONSE},
)
async def get_time_record_timeline(
        id: int,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> list[TimeRecordTimelineResponse]:
    return await service.get_record_timeline(record_id=id)


@router.get(
    "/receipt/{short_id}",
    responses={**NOT_FOUND_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def get_receipt(
        short_id: str,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> ReceiptResponse:
    return await service.get_receipt_data(short_id=short_id, current_user=current_user)


@router.get(
    "/receipt/{short_id}/pdf",
    response_class=Response,
    responses={**NOT_FOUND_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def get_receipt_pdf(
        short_id: str,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> Response:
    pdf_bytes, filename = await service.get_receipt_pdf(short_id=short_id, current_user=current_user)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
