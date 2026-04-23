from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.schemas.report import (
    MonthlyReportResponse,
    AdvancedUserReportResponse,
    DashboardMetricsResponse
)
from app.services.report_service import report_service

router = APIRouter()


def check_report_permission(current_user: User):
    is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
    if not is_manager and not current_user.can_export_report:
        raise HTTPException(
            status_code=403,
            detail="O usuário não possui privilégios suficientes para acessar relatórios globais."
        )
    return True


@router.get("/dashboard", response_model=DashboardMetricsResponse)
def get_dashboard(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    check_report_permission(current_user)
    return report_service.get_dashboard_metrics(db)


@router.get("/me", response_model=AdvancedUserReportResponse)
def get_my_report(
        month: int = Query(None, ge=1, le=12),
        year: int = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    report = report_service.get_advanced_user_report(db, current_user.id, month, year, current_user)
    if not report:
        raise HTTPException(status_code=404, detail="Report data not found")

    return report


@router.get("/monthly", response_model=MonthlyReportResponse)
def get_monthly_global_report(
        month: int = Query(None, ge=1, le=12),
        year: int = Query(None, ge=2000),
        employee_ids: Optional[List[int]] = Query(None),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    check_report_permission(current_user)
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    return report_service.get_monthly_summary(db, month, year, employee_ids, current_user)


@router.get("/export/excel")
def export_monthly_report_excel(
        month: int = Query(None, ge=1, le=12),
        year: int = Query(None, ge=2000),
        employee_ids: Optional[List[int]] = Query(None),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
):
    check_report_permission(current_user)
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    file_stream = report_service.generate_excel_report(db, month, year, employee_ids, current_user)

    filename = f"folha_ponto_{month}_{year}.xlsx"
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/user/{user_id}", response_model=AdvancedUserReportResponse)
def get_user_detailed_report(
        user_id: int,
        month: int = Query(None, ge=1, le=12),
        year: int = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
    if not is_manager and not current_user.can_export_report and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Sem permissão para ver relatório de outros usuários.")

    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    report = report_service.get_advanced_user_report(db, user_id, month, year, current_user)
    if not report:
        raise HTTPException(status_code=404, detail="User not found or data missing")

    return report
