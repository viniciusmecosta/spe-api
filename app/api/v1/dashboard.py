from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.report import ManagerDashboardResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter()


@router.get(
    "/manager",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Sem permissão para acessar este dashboard."},
    },
)
def get_manager_dashboard(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> ManagerDashboardResponse:
    return dashboard_service.get_manager_dashboard(db, current_user)
