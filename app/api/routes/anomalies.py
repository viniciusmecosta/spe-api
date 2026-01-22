from calendar import monthrange
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_db, get_current_user
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.schemas.anomaly import AnomalyResponse
from app.services.anomaly_service import anomaly_service

router = APIRouter()


def _get_query_dates(month: int, year: int) -> tuple[date, date]:
    today = date.today()

    try:
        _, last_day = monthrange(year, month)
    except ValueError:
        raise HTTPException(status_code=400, detail="Mês ou ano inválido.")

    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    if end_date >= today:
        end_date = today - timedelta(days=1)

    return start_date, end_date


@router.get("/my", response_model=List[AnomalyResponse])
def get_my_anomalies(
        month: int,
        year: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    start_date, end_date = _get_query_dates(month, year)

    if start_date > end_date:
        return []

    all_anomalies = anomaly_service.get_anomalies(db, start_date, end_date, user_id=current_user.id)

    employee_types = ["MISSING_ENTRY", "DOUBLE_ENTRY", "DOUBLE_EXIT", "MISSING_EXIT"]

    filtered = [a for a in all_anomalies if a.type in employee_types]
    return filtered


@router.get("/all", response_model=List[AnomalyResponse])
def get_all_anomalies(
        month: int,
        year: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    start_date, end_date = _get_query_dates(month, year)

    if start_date > end_date:
        return []

    return anomaly_service.get_anomalies(db, start_date, end_date)


@router.get("/user/{user_id}", response_model=List[AnomalyResponse])
def get_user_anomalies(
        user_id: int,
        month: int,
        year: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    start_date, end_date = _get_query_dates(month, year)

    if start_date > end_date:
        return []

    return anomaly_service.get_anomalies(db, start_date, end_date, user_id=user_id)
