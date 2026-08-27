import logging
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.devices.device_models import UserBiometric
from app.shared import deps

logger = logging.getLogger(__name__)


class BiometricService:
    def __init__(self, db: Annotated[Session, Depends(deps.get_db)] = None):
        self.db = db

    def get_available_sensor_indices(self, db: Session | None = None) -> list[int]:
        session = db if db is not None else self.db
        assert session is not None
        stmt = select(func.max(UserBiometric.sensor_index))
        max_index = session.scalar(stmt)
        start_index = (max_index + 1) if max_index is not None else 1
        if start_index > 127:
            return []
        return list(range(start_index, 128))


biometric_service = BiometricService()
