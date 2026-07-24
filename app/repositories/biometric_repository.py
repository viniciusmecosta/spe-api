
from sqlalchemy.orm import Session

from app.domain.models.biometric import UserBiometric
from app.domain.models.enums import UserRole
from app.domain.models.user import User


class BiometricRepository:
    def get_by_sensor_index(self, db: Session, sensor_index: int) -> UserBiometric | None:
        return db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_index).first()

    def get_manager_with_biometric(self, db: Session) -> User | None:
        return db.query(User).join(UserBiometric).filter(
            User.role.in_([UserRole.MANAGER, UserRole.MAINTAINER]),
            User.is_active == True
        ).first()


biometric_repository = BiometricRepository()
