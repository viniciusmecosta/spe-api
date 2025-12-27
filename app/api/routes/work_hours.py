from typing import Any
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api import deps
from app.schemas.work_hour import WorkHourBalanceResponse
from app.services.work_hour_service import work_hour_service
from app.domain.models.user import User

router = APIRouter()


@router.get("/my", response_model=WorkHourBalanceResponse)
def get_my_work_hours(
        start_date: date = Query(None),
        end_date: date = Query(None),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Get work hours balance for the current user.
    Defaults to the current month if dates are not provided.
    """
    if not start_date:
        today = datetime.now().date()
        start_date = date(today.year, today.month, 1)

    if not end_date:
        # Pega o último dia do mês atual (truque: dia 1 do próximo mês - 1 dia)
        today = datetime.now().date()
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        end_date = next_month - timedelta(days=1)

    return work_hour_service.calculate_balance(db, current_user.id, start_date, end_date)