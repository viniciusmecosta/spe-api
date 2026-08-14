from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api import deps
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

router = APIRouter()


@router.post(
    "/entry",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Erro de batida ou permissão negada"},
        401: {"description": "Não autenticado"},
    },
)
def register_entry(
    request: Request,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    return time_record_service.register_entry(db, current_user.id, request)


@router.post(
    "/exit",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Erro de batida ou permissão negada"},
        401: {"description": "Não autenticado"},
    },
)
def register_exit(
    request: Request,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    return time_record_service.register_exit(db, current_user.id, request)


@router.put(
    "/{id}/toggle",
    responses={
        400: {"description": "Período fechado ou erro na alternância"},
        401: {"description": "Não autenticado"},
        404: {"description": "Registro não encontrado"},
    },
)
def toggle_record_type(
    id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> TimeRecordResponse:
    return time_record_service.toggle_record_type(db, id, current_user)


@router.get(
    "/my",
    responses={
        401: {"description": "Não autenticado"},
    },
)
def read_my_records(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    skip: int = 0,
    limit: int = 100,
) -> list[TimeRecordResponse]:
    return time_record_service.get_my_records(db, current_user.id, skip, limit)


@router.get(
    "/admin/list",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
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
    responses={
        400: {"description": "Período fechado ou dados inválidos"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
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
    responses={
        400: {"description": "Período fechado ou dados inválidos"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Registro não encontrado"},
    },
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
    responses={
        400: {"description": "Período fechado"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Registro não encontrado"},
    },
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
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
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
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def trigger_tolerance_cron() -> SuccessResponse:
    tolerance_cron_service.process_unverified_entries()
    return SuccessResponse(
        status="success", message="Rotina de tolerância acionada e concluída com sucesso."
    )
