from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.repositories.audit_repository import audit_repository
from app.schemas.audit import AuditLogResponse

router = APIRouter()


@router.get("/", response_model=List[AuditLogResponse])
def read_audit_logs(
        action: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        order_by: str = Query("desc", pattern="^(asc|desc)$"),
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
):
    return audit_repository.get_logs(
        db, action=action, start_date=start_date, end_date=end_date,
        order_by=order_by, skip=skip, limit=limit
    )


@router.get("/manual-changes", response_model=List[AuditLogResponse])
def read_manual_changes(
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        order_by: str = Query("desc", pattern="^(asc|desc)$"),
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
):
    return audit_repository.get_manual_changes(
        db, start_date=start_date, end_date=end_date,
        order_by=order_by, skip=skip, limit=limit
    )
