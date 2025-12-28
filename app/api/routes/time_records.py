from typing import Any, List
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.orm import Session
from app.api import deps
from app.schemas.time_record import TimeRecordResponse, TimeRecordCreateAdmin, TimeRecordUpdate
from app.services.time_record_service import time_record_service
from app.repositories.time_record_repository import time_record_repository
from app.domain.models.user import User

router = APIRouter()

@router.post("/entry", response_model=TimeRecordResponse)
def register_entry(
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_service.register_entry(db, current_user.id, request.client.host)

@router.post("/exit", response_model=TimeRecordResponse)
def register_exit(
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_service.register_exit(db, current_user.id, request.client.host)

@router.put("/{id}/toggle", response_model=TimeRecordResponse)
def toggle_record_type(
    id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_service.toggle_record_type(db, id, current_user.id)

@router.get("/my", response_model=list[TimeRecordResponse])
def read_my_records(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return time_record_repository.get_all_by_user(db, current_user.id, skip, limit)

# --- ROTAS ADMINISTRATIVAS ---

@router.get("/admin/list", response_model=List[TimeRecordResponse])
def list_records_for_admin(
    user_id: int,
    start_date: datetime,
    end_date: datetime,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    # Rota para o gestor pegar todas as batidas de um funcionário num período
    # para exibir na tela de edição.
    records = time_record_repository.get_by_range(db, user_id, start_date, end_date)
    return records

@router.post("/admin", response_model=TimeRecordResponse)
def create_time_record_admin(
    record_in: TimeRecordCreateAdmin,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return time_record_service.create_admin_record(db, record_in, current_user.id)

@router.put("/admin/{record_id}", response_model=TimeRecordResponse)
def update_time_record_admin(
    record_id: int,
    record_in: TimeRecordUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return time_record_service.update_admin_record(db, record_id, record_in, current_user.id)

@router.delete("/admin/{record_id}")
def delete_time_record_admin(
    record_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_manager)
) -> Any:
    time_record_service.delete_admin_record(db, record_id, current_user.id)
    return {"status": "success", "message": "Record deleted"}