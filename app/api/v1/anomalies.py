from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_manager, get_db
from app.schemas.anomaly import AnomalyResponse
from app.services.anomaly_service import anomaly_service

router = APIRouter()


@router.get(
    "/all",
    dependencies=[Depends(get_current_manager)],
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
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
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def get_user_anomalies(
    user_id: int,
    month: int,
    year: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[AnomalyResponse]:
    return anomaly_service.get_anomalies_by_month(db, month, year, user_id=user_id)
