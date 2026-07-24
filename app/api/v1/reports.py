from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, List, Optional

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.schemas.report import (
    AdvancedUserReportResponse,
    DashboardMetricsResponse,
    HistoryResponse,
    MyDashboardResponse,
    TeamHoursResponse
)
from app.services.dashboard_service import dashboard_service
from app.services.excel_service import excel_service
from app.services.report_service import report_service

router = APIRouter()


def _validate_excel_export_permission(db: Session, current_user: User, month: int, year: int, now: datetime):
    is_maintainer = current_user.role == UserRole.MAINTAINER
    is_manager = current_user.role == UserRole.MANAGER

    if is_maintainer:
        return

    if is_manager:
        from app.domain.models.adjustment import AdjustmentRequest
        from app.domain.models.enums import AdjustmentStatus
        from sqlalchemy import extract

        pending_adjustments = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.status == AdjustmentStatus.PENDING,
            extract('month', AdjustmentRequest.target_date) == month,
            extract('year', AdjustmentRequest.target_date) == year
        ).first()

        if pending_adjustments:
            raise HTTPException(
                status_code=400,
                detail="Não é possível gerar o relatório pois existem ajustes pendentes neste mês."
            )
        return

    if not current_user.can_export_report:
        raise HTTPException(status_code=403, detail="Você não tem permissão para gerar relatórios.")

    prev_month = now.month - 1 if now.month > 1 else 12
    prev_year = now.year if now.month > 1 else now.year - 1

    if month != prev_month or year != prev_year:
        raise HTTPException(
            status_code=400,
            detail="Funcionários só podem gerar o relatório referente ao mês anterior."
        )

    from app.domain.models.payroll import PayrollClosure
    payroll_closed = db.query(PayrollClosure).filter(
        PayrollClosure.month == month,
        PayrollClosure.year == year,
        PayrollClosure.is_closed == True,
        PayrollClosure.deleted_at.is_(None)
    ).first()

    if not payroll_closed:
        raise HTTPException(
            status_code=400,
            detail="Não é possível gerar o relatório pois a folha deste mês ainda não está fechada."
        )


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
    return dashboard_service.get_dashboard_metrics(db)


@router.get("/my/dashboard", response_model=MyDashboardResponse)
def get_my_dashboard(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return dashboard_service.get_my_dashboard(db, current_user)


@router.get("/history/me", response_model=HistoryResponse)
def get_my_history(
        month: Optional[int] = Query(None, ge=1, le=12),
        year: Optional[int] = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    return report_service.get_history_report(db, current_user.id, month, year, current_user)


@router.get("/history/user/{user_id}", response_model=HistoryResponse)
def get_user_history(
        user_id: int,
        month: Optional[int] = Query(None, ge=1, le=12),
        year: Optional[int] = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
    if not is_manager and not current_user.can_export_report and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar o histórico deste usuário.")
    
    return report_service.get_history_report(db, user_id, month, year, current_user)


@router.get("/team-hours", response_model=TeamHoursResponse)
def get_team_hours(
        month: Optional[int] = Query(None, ge=1, le=12),
        year: Optional[int] = Query(None, ge=2000),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    check_report_permission(current_user)
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    return dashboard_service.get_team_worked_hours(db, month, year, current_user)


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

    _validate_excel_export_permission(db, current_user, month, year, now)

    file_stream = excel_service.generate_excel_report(db, month, year, employee_ids, current_user)

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
