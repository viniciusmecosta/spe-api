from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.devices.device_models import UserBiometric
from app.features.users.user_exceptions import BiometricValidationError
from app.features.users.user_models import User


class UserBiometricService:
    def _get_bio_attr(self, bio_data: Any, attr: str) -> Any:
        if isinstance(bio_data, dict):
            return bio_data.get(attr)
        return getattr(bio_data, attr, None)

    def validate_sensor_index(
        self, db: Session, user: User, sensor_idx: int | None, seen_indices: set[int]
    ) -> None:
        if sensor_idx is None:
            return
        if sensor_idx in seen_indices:
            raise BiometricValidationError(f"Índice biométrico {sensor_idx} enviado em duplicidade.")
        seen_indices.add(sensor_idx)

        stmt = select(UserBiometric).where(UserBiometric.sensor_index == sensor_idx)
        if getattr(user, "id", None):
            stmt = stmt.where(UserBiometric.user_id != user.id)
        if db.scalar(select(stmt.exists())):
            raise BiometricValidationError(f"Índice biométrico {sensor_idx} já cadastrado em outro usuário.")

    def validate_finger_id(self, finger_id: int | None, seen_fingers: set[int]) -> None:
        if finger_id is None:
            return
        if finger_id in seen_fingers:
            raise BiometricValidationError(f"Biometria {finger_id} enviada em duplicidade.")
        seen_fingers.add(finger_id)

    def process_single_biometric(
        self,
        db: Session,
        user: User,
        bio_data: Any,
        seen_indices: set[int],
        seen_fingers: set[int],
        current_biometrics: dict[int, UserBiometric],
    ) -> UserBiometric:
        bio_id = self._get_bio_attr(bio_data, "id")
        sensor_idx = self._get_bio_attr(bio_data, "sensor_index")
        tmpl_data = self._get_bio_attr(bio_data, "template_data")
        finger_id = self._get_bio_attr(bio_data, "finger_id")

        self.validate_sensor_index(db, user, sensor_idx, seen_indices)
        self.validate_finger_id(finger_id, seen_fingers)

        if bio_id and bio_id in current_biometrics:
            existing = current_biometrics[bio_id]
            existing.sensor_index = sensor_idx
            if tmpl_data is not None:
                existing.template_data = tmpl_data
            existing.finger_id = finger_id
            return existing

        return UserBiometric(
            sensor_index=sensor_idx,
            template_data=tmpl_data,
            finger_id=finger_id,
        )

    def sync_biometrics(self, db: Session, user: User, biometrics_in: list[Any]) -> None:
        current_biometrics = {b.id: b for b in user.biometrics} if getattr(user, "id", None) else {}
        new_biometrics_list: list[UserBiometric] = []
        seen_indices: set[int] = set()
        seen_fingers: set[int] = set()

        for bio_data in biometrics_in:
            processed_bio = self.process_single_biometric(
                db, user, bio_data, seen_indices, seen_fingers, current_biometrics
            )
            new_biometrics_list.append(processed_bio)

        user.biometrics = new_biometrics_list


user_biometric_service = UserBiometricService()
