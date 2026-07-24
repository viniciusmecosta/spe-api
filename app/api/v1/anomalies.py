
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_manager, get_db
from app.domain.models.user import User
from app.schemas.anomaly import AnomalyResponse
from app.services.anomaly_service import anomaly_service

router = APIRouter()


@router.get("/all", response_model=list[AnomalyResponse])
def get_all_anomalies(
        month: int,
        year: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_manager),
):
    return anomaly_service.get_anomalies_by_month(db, month, year)


@router.get("/user/{user_id}", response_model=list[AnomalyResponse])
def get_user_anomalies(
        user_id: int,
        month: int,
        year: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_manager),
):
    return anomaly_service.get_anomalies_by_month(db, month, year, user_id=user_id)
