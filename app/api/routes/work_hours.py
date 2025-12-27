from typing import Any
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.api import deps
from app.schemas.work_hour import WorkHourBalanceResponse
from app.services.work_hour_service import work_hour_service
from app.repositories.user_repository import user_repository
from app.domain.models.user import User

router = APIRouter()


def _get_default_dates(start_date: date | None, end_date: date | None):
    if not start_date:
        today = datetime.now().date()
        start_date = date(today.year, today.month, 1)

    if not end_date:
        today = datetime.now().date()
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        end_date = next_month - timedelta(days=1)
    return start_date, end_date


@router.get("/my", response_model=WorkHourBalanceResponse)
def get_my_work_hours(
        start_date: date = Query(None),
        end_date: date = Query(None),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Get work hours balance for the current user.
    """
    start_date, end_date = _get_default_dates(start_date, end_date)
    return work_hour_service.calculate_balance(db, current_user.id, start_date, end_date)


@router.get("/user/{user_id}", response_model=WorkHourBalanceResponse)
def get_user_work_hours(
        user_id: int,
        start_date: date = Query(None),
        end_date: date = Query(None),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    """
    Get work hours balance for a specific user. (Manager only)
    """
    if not user_repository.get(db, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    start_date, end_date = _get_default_dates(start_date, end_date)
    return work_hour_service.calculate_balance(db, user_id, start_date, end_date)


@router.get("/all", response_model=list[WorkHourBalanceResponse])
def get_all_work_hours(
        start_date: date = Query(None),
        end_date: date = Query(None),
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_manager)
) -> Any:
    """
    Get work hours balance for all users. (Manager only)
    """
    start_date, end_date = _get_default_dates(start_date, end_date)
    users = user_repository.get_multi(db, limit=1000)

    results = []
    for user in users:
        results.append(work_hour_service.calculate_balance(db, user.id, start_date, end_date))

    return results