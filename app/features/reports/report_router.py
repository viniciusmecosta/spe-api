from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.features.reports.dashboard_service import DashboardService
from app.features.reports.excel_service import ExcelService
from app.features.reports.report_schemas import (
    AdvancedUserReportResponse,
    DashboardMetricsResponse,
    HistoryResponse,
    ManagerDashboardResponse,
    MyDashboardResponse,
    TeamHoursResponse,
)
from app.features.reports.report_service import ReportService
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
        report_service: Annotated[ReportService, Depends()],
        dashboard_service: Annotated[DashboardService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> DashboardMetricsResponse:
    report_service.check_report_permission(current_user)
    return await dashboard_service.get_dashboard_metrics()


@router.get("/my/dashboard")
async def get_my_dashboard(
        dashboard_service: Annotated[DashboardService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> MyDashboardResponse:
    return await dashboard_service.get_my_dashboard(current_user=current_user)


@router.get("/history/me")
async def get_my_history(
        report_service: Annotated[ReportService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
) -> HistoryResponse:
    return await report_service.get_history_report(user_id=current_user.id, month=month, year=year,
                                                   current_user=current_user)


@router.get(
    "/history/user/{user_id}",
    responses={**FORBIDDEN_RESPONSE},
)
async def get_user_history(
        user_id: int,
        report_service: Annotated[ReportService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
) -> HistoryResponse:
    report_service.check_user_report_access(
        current_user, user_id, detail="Sem permissão para acessar o histórico deste usuário."
    )
    return await report_service.get_history_report(user_id=user_id, month=month, year=year, current_user=current_user)


@router.get(
    "/team-hours",
    responses={**FORBIDDEN_RESPONSE},
)
async def get_team_hours(
        report_service: Annotated[ReportService, Depends()],
        dashboard_service: Annotated[DashboardService, Depends()],
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

    return await dashboard_service.get_team_worked_hours(month=month, year=year, current_user=current_user)


@router.get(
    "/export/excel",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def export_monthly_report_excel(
        report_service: Annotated[ReportService, Depends()],
        excel_service: Annotated[ExcelService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        year: Annotated[int | None, Query(ge=2000)] = None,
        employee_ids: Annotated[list[int] | None, Query()] = None,
) -> Response:
    report_service.check_report_permission(current_user)
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    await report_service.validate_excel_export_permission(current_user=current_user, month=month, year=year, now=now)

    return await excel_service.export_monthly_report(
        month=month,
        year=year,
        employee_ids=employee_ids,
        current_user=current_user,
    )


@router.get(
    "/user/{user_id}",
    responses={**CRUD_RESPONSES},
)
async def get_user_detailed_report(
        user_id: int,
        report_service: Annotated[ReportService, Depends()],
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

    return await report_service.get_advanced_user_report_or_404(user_id=user_id, month=month, year=year,
                                                                current_user=current_user)


@dashboard_router.get("/manager")
async def get_manager_dashboard(
        dashboard_service: Annotated[DashboardService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> ManagerDashboardResponse:
    return await dashboard_service.get_manager_dashboard(current_user=current_user)
