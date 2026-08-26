import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.devices.device_models import UserBiometric

logger = logging.getLogger(__name__)


class BiometricService:
    def get_available_sensor_indices(self, db: Session) -> list[int]:
        stmt = select(func.max(UserBiometric.sensor_index))
        max_index = db.scalar(stmt)
        start_index = (max_index + 1) if max_index is not None else 1
        if start_index > 127:
            return []
        return list(range(start_index, 128))


biometric_service = BiometricService()
