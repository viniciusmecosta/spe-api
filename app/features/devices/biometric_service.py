import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.devices.device_models import UserBiometric

logger = logging.getLogger(__name__)


class BiometricService:
    def get_available_sensor_indices(self, db: Session) -> list[int]:
        stmt = select(UserBiometric.sensor_index).where(UserBiometric.sensor_index.isnot(None))
        raw_indices = db.scalars(stmt).all()
        used_indices = {
            item[0] if isinstance(item, (tuple, list)) else item
            for item in raw_indices
        }

        all_possible_indices = set(range(1, 128))
        available_indices = all_possible_indices - used_indices
        return sorted(available_indices)


biometric_service = BiometricService()
