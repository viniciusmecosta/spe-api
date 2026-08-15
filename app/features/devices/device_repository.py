from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.security import get_api_key_hash
from app.domain.enums import UserRole
from app.features.users.user_models import User
from app.features.devices.device_models import (
    DeviceCredential,
    Firmware,
    UserBiometric,
)
from app.features.devices.device_schemas import (
    DeviceCredentialCreate,
    DeviceCredentialUpdate,
)


class DeviceCredentialRepository:
    def create(self, db: Session, obj_in: DeviceCredentialCreate) -> DeviceCredential:
        hashed_key = get_api_key_hash(obj_in.api_key)
        db_obj = DeviceCredential(
            name=obj_in.name,
            key_type=obj_in.key_type,
            api_key_hash=hashed_key,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> DeviceCredential | None:
        return db.query(DeviceCredential).filter(DeviceCredential.id == id).first()

    def get_all(self, db: Session) -> list[DeviceCredential]:
        return db.query(DeviceCredential).all()

    def update(self, db: Session, db_obj: DeviceCredential, obj_in: DeviceCredentialUpdate) -> DeviceCredential:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: int):
        db.query(DeviceCredential).filter(DeviceCredential.id == id).delete()
        db.commit()


class FirmwareRepository:
    def get_by_version(self, db: Session, version: str) -> Firmware | None:
        return db.query(Firmware).filter(Firmware.version == version).order_by(desc(Firmware.created_at)).first()

    def get_latest(self, db: Session) -> Firmware | None:
        return db.query(Firmware).order_by(desc(Firmware.created_at)).first()

    def get_all(self, db: Session) -> list[Firmware]:
        return db.query(Firmware).order_by(desc(Firmware.created_at)).all()

    def create(self, db: Session, version: str, file_path: str) -> Firmware:
        db_obj = Firmware(version=version, file_path=file_path)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


class BiometricRepository:
    def get_by_sensor_index(self, db: Session, sensor_index: int) -> UserBiometric | None:
        return db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_index).first()

    def get_manager_with_biometric(self, db: Session) -> User | None:
        return db.query(User).join(UserBiometric).filter(
            User.role.in_([UserRole.MANAGER, UserRole.MAINTAINER]),
            User.is_active == True
        ).first()


device_credential_repository = DeviceCredentialRepository()
firmware_repository = FirmwareRepository()
biometric_repository = BiometricRepository()
