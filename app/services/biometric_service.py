import logging
from sqlalchemy.orm import Session
from typing import List

from app.domain.models.biometric import UserBiometric
from app.domain.models.user import User
from app.schemas.mqtt import BiometricSyncData, EnrollResultPayload

logger = logging.getLogger(__name__)


class BiometricService:
    def get_all_for_sync(self, db: Session) -> List[BiometricSyncData]:
        biometrics = db.query(UserBiometric).join(User).filter(
            User.is_active == True,
            UserBiometric.template_data.isnot(None)
        ).all()

        result = []
        for bio in biometrics:
            result.append(BiometricSyncData(
                biometric_id=bio.id,
                template_data=bio.template_data,
                user_id=bio.user_id
            ))
        return result

    def save_enrolled_biometric(self, db: Session, result: EnrollResultPayload):
        try:
            if not result.success:
                return False, result.error

            user = db.query(User).filter(User.id == result.user_id).first()
            if not user:
                return False, "Usuario nao encontrado"

            new_bio = UserBiometric(
                user_id=user.id,
                template_data=result.template_data,
                sensor_index=result.sensor_index
            )
            db.add(new_bio)
            db.commit()
            return True, "Sucesso"
        except Exception as e:
            logger.error(f"Erro Enroll: {e}")
            return False, str(e)


biometric_service = BiometricService()