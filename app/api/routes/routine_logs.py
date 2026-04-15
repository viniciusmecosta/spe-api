from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api import deps
from app.domain.models.user import User
from app.repositories.routine_log_repository import routine_log_repository
from app.schemas.routine_log import RoutineLogResponse

router = APIRouter()


@router.get("/", response_model=List[RoutineLogResponse])
def read_routine_logs(
        routine_type: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        order_by: str = Query("desc", pattern="^(asc|desc)$"),
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    return routine_log_repository.get_logs(
        db,
        routine_type=routine_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit
    )
