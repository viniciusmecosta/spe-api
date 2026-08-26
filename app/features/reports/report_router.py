from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.features.reports.dashboard_service import dashboard_service
from app.features.reports.excel_service import excel_service
from app.features.reports.report_schemas import (
    AdvancedUserReportResponse,
    DashboardMetricsResponse,
    HistoryResponse,
    ManagerDashboardResponse,
    MyDashboardResponse,
    TeamHoursResponse,
)
from app.features.reports.report_service import report_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})
dashboard_router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/dashboard",
    responses={**FORBIDDEN_RESPONSE},
)
async def get_dashboard(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> DashboardMetricsResponse:
    report_service.check_report_permission(current_user)
    return dashboard_service.get_dashboard_metrics(db)


@router.get("/my/dashboard")
async def get_my_dashboard(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> MyDashboardResponse:
    return dashboard_service.get_my_dashboard(db, current_user)


@router.get("/history/me")
async def get_my_history(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
) -> HistoryResponse:
    return report_service.get_history_report(db, current_user.id, month, year, current_user)


@router.get(
    "/history/user/{user_id}",
    responses={**FORBIDDEN_RESPONSE},
)
async def get_user_history(
        user_id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
) -> HistoryResponse:
    report_service.check_user_report_access(
        current_user, user_id, detail="Sem permissão para acessar o histórico deste usuário."
    )
    return report_service.get_history_report(db, user_id, month, year, current_user)


@router.get(
    "/team-hours",
    responses={**FORBIDDEN_RESPONSE},
)
async def get_team_hours(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
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
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def export_monthly_report_excel(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
        employee_ids: Annotated[list[int] | None, Query()] = None,
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
    responses={**CRUD_RESPONSES},
)
async def get_user_detailed_report(
        user_id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
) -> AdvancedUserReportResponse:
    report_service.check_user_report_access(
        current_user, user_id, detail="Sem permissão para ver relatório de outros usuários."
    )

    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    return report_service.get_advanced_user_report_or_404(db, user_id, month, year, current_user)


@dashboard_router.get("/manager")
async def get_manager_dashboard(
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> ManagerDashboardResponse:
    return dashboard_service.get_manager_dashboard(db, current_user)
