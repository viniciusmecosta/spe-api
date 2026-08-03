from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.schemas.report import ManagerDashboardResponse
from app.services.dashboard_service import dashboard_service

router = APIRouter()


@router.get("/manager", response_model=ManagerDashboardResponse)
def get_manager_dashboard(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Retorna o dashboard consolidado para gestores e mantenedores.
    """
    if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este dashboard.")
        
    return dashboard_service.get_manager_dashboard(db, current_user)
