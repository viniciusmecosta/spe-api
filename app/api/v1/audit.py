from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.audit import AuditLogResponse
from app.services.audit_service import audit_service

router = APIRouter()


@router.get("/", response_model=list[AuditLogResponse])
def read_audit_logs(
        action: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: str = Query("desc", pattern="^(asc|desc)$"),
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
):
    return audit_service.get_logs(
        db, action=action, start_date=start_date, end_date=end_date,
        order_by=order_by, skip=skip, limit=limit
    )
