from datetime import datetime
from typing import Annotated

from app.api import deps
from app.api.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from app.core.security import get_client_device_name, get_client_ip
from app.domain.models.user import User
from app.schemas.time_record import (
    SuccessResponse,
    TimeRecordCreateAdmin,
    TimeRecordDeleteAdmin,
    TimeRecordResponse,
    TimeRecordTimelineResponse,
    TimeRecordUpdate,
)
from app.services.time_record_service import time_record_service
from app.services.tolerance_cron_service import tolerance_cron_service
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.post(
    "/entry",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE},
)
def register_entry(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    record = time_record_service.register_entry(db, current_user.id, request)
    time_record_service.trigger_auto_print(db, record, background_tasks)
    return record


@router.post(
    "/exit",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE},
)
def register_exit(
        request: Request,
        background_tasks: BackgroundTasks,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    record = time_record_service.register_exit(db, current_user.id, request)
    time_record_service.trigger_auto_print(db, record, background_tasks)
    return record


@router.put(
    "/{id}/toggle",
    responses={**BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)
def toggle_record_type(
        id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    return time_record_service.toggle_record_type(db, id, current_user)


@router.get("/my")
def read_my_records(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        skip: int = 0,
        limit: int = 100,
) -> list[TimeRecordResponse]:
    return time_record_service.get_my_records(db, current_user.id, skip, limit)


@router.get(
    "/admin/list",
    responses={**FORBIDDEN_RESPONSE},
)
def list_records_for_admin(
        user_id: int,
        start_date: datetime,
        end_date: datetime,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> list[TimeRecordResponse]:
    return time_record_service.list_records_for_admin(db, user_id, start_date, end_date)


@router.post(
    "/admin",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
def create_time_record_admin(
        record_in: TimeRecordCreateAdmin,
        request: Request,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> TimeRecordResponse:
    ip_address = get_client_ip(request)
    device_name = get_client_device_name(ip_address, request)
    platform = request.headers.get("X-Platform", "desktop").lower()
    return time_record_service.create_admin_record(
        db, record_in, current_user.id, ip_address, device_name, platform
    )


@router.put(
    "/admin/{record_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def update_time_record_admin(
        record_id: int,
        record_in: TimeRecordUpdate,
        request: Request,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> TimeRecordResponse:
    ip_address = get_client_ip(request)
    device_name = get_client_device_name(ip_address, request)
    platform = request.headers.get("X-Platform", "desktop").lower()
    return time_record_service.update_admin_record(
        db, record_id, record_in, current_user.id, ip_address, device_name, platform
    )


@router.delete(
    "/admin/{record_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def delete_time_record_admin(
        record_id: int,
        request_body: TimeRecordDeleteAdmin,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> SuccessResponse:
    time_record_service.delete_admin_record(db, record_id, request_body, current_user.id)
    return SuccessResponse(status="success", message="Record deleted")


@router.get(
    "/{id}/timeline",
    responses={**FORBIDDEN_RESPONSE},
)
def get_time_record_timeline(
        id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> list[TimeRecordTimelineResponse]:
    return time_record_service.get_record_timeline(db, id)


@router.post(
    "/admin/tolerance/process",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**FORBIDDEN_RESPONSE},
)
def trigger_tolerance_cron() -> SuccessResponse:
    tolerance_cron_service.process_unverified_entries()
    return SuccessResponse(
        status="success", message="Rotina de tolerância acionada e concluída com sucesso."
    )


@router.get("/receipt/{short_id}")
def get_receipt(
    short_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    return time_record_service.get_receipt_data(db, short_id, current_user)


@router.get("/receipt/{short_id}/pdf", response_class=Response)
def get_receipt_pdf(
    short_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    from app.services.hashid_service import hashid_service
    nsr = hashid_service.decode(short_id)
    if not nsr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid receipt ID")
        
    pdf_bytes = time_record_service.get_receipt_pdf(db, short_id, current_user)
    headers = {
        "Content-Disposition": f'attachment; filename="{nsr}.pdf"'
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
