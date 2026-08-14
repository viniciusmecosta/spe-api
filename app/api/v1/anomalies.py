from typing import Annotated

from app.api.deps import get_current_manager, get_db
from app.api.openapi_responses import AUTH_RESPONSES
from app.schemas.anomaly import AnomalyResponse
from app.services.anomaly_service import anomaly_service
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(responses={**AUTH_RESPONSES})


@router.get(
    "/all",
    dependencies=[Depends(get_current_manager)],
)
def get_all_anomalies(
        month: int,
        year: int,
        db: Annotated[Session, Depends(get_db)],
) -> list[AnomalyResponse]:
    return anomaly_service.get_anomalies_by_month(db, month, year)


@router.get(
    "/user/{user_id}",
    dependencies=[Depends(get_current_manager)],
)
def get_user_anomalies(
        user_id: int,
        month: int,
        year: int,
        db: Annotated[Session, Depends(get_db)],
) -> list[AnomalyResponse]:
    return anomaly_service.get_anomalies_by_month(db, month, year, user_id=user_id)
