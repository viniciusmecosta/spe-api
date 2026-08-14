from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.api.openapi_responses import AUTH_RESPONSES
from app.schemas.audit import AuditLogResponse
from app.services.audit_service import audit_service

router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_manager)],
)
def read_audit_logs(
    db: Annotated[Session, Depends(deps.get_db)],
    action: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    order_by: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    skip: int = 0,
    limit: int = 100,
) -> list[AuditLogResponse]:
    return audit_service.get_logs(
        db,
        action=action,
        start_date=start_date,
        end_date=end_date,
        order_by=order_by,
        skip=skip,
        limit=limit,
    )
