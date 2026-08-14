from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.api.openapi_responses import AUTH_RESPONSES
from app.schemas.routine_log import RoutineLogResponse
from app.services.routine_log_service import routine_log_service

router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
)
def read_routine_logs(
    db: Annotated[Session, Depends(deps.get_db)],
    routine_type: str | None = None,
    status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    order_by: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    skip: int = 0,
    limit: int = 100,
) -> list[RoutineLogResponse]:
    return routine_log_service.get_logs(
        db,
        routine_type=routine_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit,
    )
