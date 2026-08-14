from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.schemas.report import (
    AdvancedUserReportResponse,
    DashboardMetricsResponse,
    HistoryResponse,
    MyDashboardResponse,
    TeamHoursResponse,
)
from app.services.dashboard_service import dashboard_service
from app.services.excel_service import excel_service
from app.services.report_service import report_service

router = APIRouter()


@router.get(
    "/dashboard",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente para relatórios globais"},
    },
)
def get_dashboard(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> DashboardMetricsResponse:
    report_service.check_report_permission(current_user)
    return dashboard_service.get_dashboard_metrics(db)


@router.get(
    "/my/dashboard",
    responses={
        401: {"description": "Não autenticado"},
    },
)
def get_my_dashboard(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> MyDashboardResponse:
    return dashboard_service.get_my_dashboard(db, current_user)


@router.get(
    "/history/me",
    responses={
        401: {"description": "Não autenticado"},
    },
)
def get_my_history(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000),
) -> HistoryResponse:
    return report_service.get_history_report(db, current_user.id, month, year, current_user)


@router.get(
    "/history/user/{user_id}",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Sem permissão para acessar o histórico deste usuário."},
    },
)
def get_user_history(
    user_id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000),
) -> HistoryResponse:
    is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
    if not is_manager and not current_user.can_export_report and current_user.id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para acessar o histórico deste usuário.",
        )

    return report_service.get_history_report(db, user_id, month, year, current_user)


@router.get(
    "/team-hours",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def get_team_hours(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000),
) -> TeamHoursResponse:
    report_service.check_report_permission(current_user)
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    return dashboard_service.get_team_worked_hours(db, month, year, current_user)


@router.get(
    "/export/excel",
    responses={
        400: {"description": "Mês inválido ou ajustes pendentes"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def export_monthly_report_excel(
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None, ge=2000),
    employee_ids: list[int] | None = Query(None),
) -> StreamingResponse:
    report_service.check_report_permission(current_user)
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    report_service.validate_excel_export_permission(db, current_user, month, year, now)

    file_stream = excel_service.generate_excel_report(db, month, year, employee_ids, current_user)

    filename = f"folha_ponto_{month}_{year}.xlsx"
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/user/{user_id}",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Sem permissão para ver relatório de outros usuários."},
        404: {"description": "User not found or data missing"},
    },
)
def get_user_detailed_report(
    user_id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None, ge=2000),
) -> AdvancedUserReportResponse:
    is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
    if not is_manager and not current_user.can_export_report and current_user.id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para ver relatório de outros usuários.",
        )

    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    report = report_service.get_advanced_user_report(db, user_id, month, year, current_user)
    if not report:
        raise HTTPException(status_code=404, detail="User not found or data missing")

    return report
