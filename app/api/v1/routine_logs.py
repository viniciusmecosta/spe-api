from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.routine_log import RoutineLogResponse
from app.services.routine_log_service import routine_log_service

router = APIRouter()


@router.get("/", response_model=list[RoutineLogResponse])
def read_routine_logs(
        routine_type: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: str = Query("desc", pattern="^(asc|desc)$"),
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    return routine_log_service.get_logs(
        db,
        routine_type=routine_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit
    )
