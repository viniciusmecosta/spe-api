from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.report import MonthlyReportResponse, UserReportResponse, DashboardMetricsResponse
from app.services.report_service import report_service

router = APIRouter()


@router.get("/dashboard", response_model=DashboardMetricsResponse)
def get_dashboard(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    return report_service.get_dashboard_metrics(db)


@router.get("/monthly", response_model=MonthlyReportResponse)
def get_monthly_global_report(
        month: int = Query(None, ge=1, le=12),
        year: int = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    now = datetime.now()
    if not month: month = now.month
    if not year: year = now.year

    return report_service.get_monthly_summary(db, month, year)


@router.get("/export/excel")
def export_monthly_report_excel(
        month: int = Query(None, ge=1, le=12),
        year: int = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
):
    now = datetime.now()
    if not month: month = now.month
    if not year: year = now.year

    file_stream = report_service.generate_excel_report(db, month, year)

    filename = f"relatorio_{month}_{year}.xlsx"
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/user/{user_id}", response_model=UserReportResponse)
def get_user_detailed_report(
        user_id: int,
        month: int = Query(None, ge=1, le=12),
        year: int = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    now = datetime.now()
    if not month: month = now.month
    if not year: year = now.year

    report = report_service.get_user_report(db, user_id, month, year)
    if not report:
        raise HTTPException(status_code=404, detail="User not found")

    return report
