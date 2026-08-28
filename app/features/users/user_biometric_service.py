from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.features.devices.device_models import UserBiometric
from app.features.users.user_exceptions import BiometricValidationError
from app.features.users.user_models import User


class UserBiometricService:
    def __init__(self, db: Annotated[AsyncSession, Depends(get_async_db)]):
        self.db = db

    def _get_bio_attr(self, bio_data: Any, attr: str) -> Any:
        if isinstance(bio_data, dict):
            return bio_data.get(attr)
        return getattr(bio_data, attr, None)

    async def validate_sensor_index(
            self, user: User, sensor_idx: int | None, seen_indices: set[int]
    ) -> None:
        if sensor_idx is None:
            return
        if sensor_idx in seen_indices:
            raise BiometricValidationError(f"Índice biométrico {sensor_idx} enviado em duplicidade.")
        seen_indices.add(sensor_idx)

        stmt = select(UserBiometric).where(UserBiometric.sensor_index == sensor_idx)
        if getattr(user, "id", None):
            stmt = stmt.where(UserBiometric.user_id != user.id)
        if await self.db.scalar(select(stmt.exists())):
            raise BiometricValidationError(f"Índice biométrico {sensor_idx} já cadastrado em outro usuário.")

    def validate_finger_id(self, finger_id: int | None, seen_fingers: set[int]) -> None:
        if finger_id is None:
            return
        if finger_id in seen_fingers:
            raise BiometricValidationError(f"Biometria {finger_id} enviada em duplicidade.")
        seen_fingers.add(finger_id)

    async def process_single_biometric(
        self,
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

        await self.validate_sensor_index(user, sensor_idx, seen_indices)
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
