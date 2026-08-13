import logging

from app.domain.models.biometric import UserBiometric
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class BiometricService:
    def get_available_sensor_indices(self, db: Session) -> list[int]:
        used_indices_query = db.query(UserBiometric.sensor_index).filter(
            UserBiometric.sensor_index.isnot(None)
        ).all()

        used_indices = {index[0] for index in used_indices_query}
        all_possible_indices = set(range(1, 128))
        available_indices = all_possible_indices - used_indices
        return sorted(available_indices)


biometric_service = BiometricService()
