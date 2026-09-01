from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.core.security import get_client_device_name, get_client_ip
from app.features.time_records.time_record_schemas import (
    ReceiptResponse,
    SuccessResponse,
    TimeRecordCreateAdmin,
    TimeRecordDeleteAdmin,
    TimeRecordResponse,
    TimeRecordTimelineResponse,
    TimeRecordUpdate,
)
from app.features.time_records.time_record_service import TimeRecordService
from app.features.users.user_models import User
from app.shared import deps
from app.shared.daily_excess_service import daily_excess_service
from app.shared.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from app.shared.tolerance_cron_service import tolerance_cron_service

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.post(
    "/entry",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE},
)
async def register_entry(
        request: Request,
        background_tasks: BackgroundTasks,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    record = await service.register_entry(user_id=current_user.id, request=request)
    await service.trigger_auto_print(record=record, background_tasks=background_tasks)
    background_tasks.add_task(daily_excess_service.evaluate_user_day_bg, current_user.id, record.record_datetime.date())
    return record


@router.post(
    "/exit",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE},
)
async def register_exit(
        request: Request,
        background_tasks: BackgroundTasks,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    record = await service.register_exit(user_id=current_user.id, request=request)
    await service.trigger_auto_print(record=record, background_tasks=background_tasks)
    background_tasks.add_task(daily_excess_service.evaluate_user_day_bg, current_user.id, record.record_datetime.date())
    return record


@router.put(
    "/{id}/toggle",
    responses={**BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def toggle_record_type(
        id: int,
        background_tasks: BackgroundTasks,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    record = await service.toggle_record_type(record_id=id, current_user=current_user)
    background_tasks.add_task(daily_excess_service.evaluate_user_day_bg, record.user_id, record.record_datetime.date())
    return record


@router.get("/my")
async def read_my_records(
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        skip: int = 0,
        limit: int = 100,
) -> list[TimeRecordResponse]:
    return await service.get_my_records(user_id=current_user.id, skip=skip, limit=limit)


@router.get(
    "/admin/list",
    responses={**FORBIDDEN_RESPONSE},
)
async def list_records_for_admin(
        user_id: int,
        start_date: datetime,
        end_date: datetime,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> list[TimeRecordResponse]:
    return await service.list_records_for_admin(user_id=user_id, start_date=start_date, end_date=end_date)


@router.post(
    "/admin",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def create_time_record_admin(
        record_in: TimeRecordCreateAdmin,
        request: Request,
        background_tasks: BackgroundTasks,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> TimeRecordResponse:
    ip_address = get_client_ip(request)
    device_name = get_client_device_name(ip_address, request)
    platform = request.headers.get("X-Platform", "desktop").lower()
    record = await service.create_admin_record(
        obj_in=record_in, manager_id=current_user.id, ip_address=ip_address, device_name=device_name, platform=platform
    )
    background_tasks.add_task(daily_excess_service.evaluate_user_day_bg, record.user_id, record.record_datetime.date())
    return record


@router.put(
    "/admin/{record_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def update_time_record_admin(
        record_id: int,
        record_in: TimeRecordUpdate,
        request: Request,
        background_tasks: BackgroundTasks,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> TimeRecordResponse:
    ip_address = get_client_ip(request)
    device_name = get_client_device_name(ip_address, request)
    platform = request.headers.get("X-Platform", "desktop").lower()
    record = await service.update_admin_record(
        record_id=record_id, obj_in=record_in, manager_id=current_user.id, ip_address=ip_address, device_name=device_name, platform=platform
    )
    background_tasks.add_task(daily_excess_service.evaluate_user_day_bg, record.user_id, record.record_datetime.date())
    return record


@router.delete(
    "/admin/{record_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def delete_time_record_admin(
        record_id: int,
        request_body: TimeRecordDeleteAdmin,
        background_tasks: BackgroundTasks,
        service: Annotated[TimeRecordService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> SuccessResponse:
    await service.delete_admin_record(record_id=record_id, obj_in=request_body, manager_id=current_user.id)
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


@router.post(
    "/admin/tolerance/process",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**FORBIDDEN_RESPONSE},
)
async def trigger_tolerance_cron() -> SuccessResponse:
    tolerance_cron_service.process_unverified_entries()
    return SuccessResponse(
        status="success", message="Rotina de tolerância acionada e concluída com sucesso."
    )


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
