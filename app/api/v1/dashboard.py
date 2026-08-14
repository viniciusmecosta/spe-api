from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.api.openapi_responses import AUTH_RESPONSES
from app.domain.models.user import User
from app.schemas.report import ManagerDashboardResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter(responses={**AUTH_RESPONSES})


@router.get("/manager")
def get_manager_dashboard(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> ManagerDashboardResponse:
    return dashboard_service.get_manager_dashboard(db, current_user)
