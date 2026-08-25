from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.security import get_api_key_hash
from app.database.repository import BaseRepository
from app.features.devices.device_models import (
    DeviceCredential,
    Firmware,
    UserBiometric,
)
from app.features.devices.device_schemas import (
    DeviceCredentialCreate,
    DeviceCredentialUpdate,
)
from app.features.users.user_models import User
from app.shared.enums import UserRole


class DeviceCredentialRepository(BaseRepository[DeviceCredential, DeviceCredentialCreate, DeviceCredentialUpdate]):
    def __init__(self):
        super().__init__(DeviceCredential)

    def create(self, db: Session, *, obj_in: DeviceCredentialCreate) -> DeviceCredential:
        hashed_key = get_api_key_hash(obj_in.api_key)
        db_obj = DeviceCredential(
            name=obj_in.name,
            key_type=obj_in.key_type,
            api_key_hash=hashed_key,
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> DeviceCredential | None:
        return super().get(db, id)

    def get_all(self, db: Session) -> list[DeviceCredential]:
        stmt = select(DeviceCredential)
        return list(db.scalars(stmt).all())

    def update(
            self, db: Session, *, db_obj: DeviceCredential, obj_in: DeviceCredentialUpdate
    ) -> DeviceCredential:
        return super().update(db, db_obj=db_obj, obj_in=obj_in)

    def delete(self, db: Session, id: int):
        super().remove(db, id=id)


class FirmwareRepository(BaseRepository[Firmware, Firmware, Firmware]):
    def __init__(self):
        super().__init__(Firmware)

    def get_by_version(self, db: Session, version: str) -> Firmware | None:
        stmt = (
            select(Firmware)
            .where(Firmware.version == version)
            .order_by(desc(Firmware.created_at))
        )
        return db.scalars(stmt).first()

    def get_latest(self, db: Session) -> Firmware | None:
        stmt = select(Firmware).order_by(desc(Firmware.created_at))
        return db.scalars(stmt).first()

    def get_all(self, db: Session) -> list[Firmware]:
        stmt = select(Firmware).order_by(desc(Firmware.created_at))
        return list(db.scalars(stmt).all())

    def create(
            self,
            db: Session,
            *,
            obj_in: Firmware | None = None,
            version: str | None = None,
            file_path: str | None = None,
    ) -> Firmware:
        if obj_in is not None:
            db_obj = obj_in
        else:
            db_obj = Firmware(version=version, file_path=file_path)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


class BiometricRepository(BaseRepository[UserBiometric, UserBiometric, UserBiometric]):
    def __init__(self):
        super().__init__(UserBiometric)

    def get_by_sensor_index(self, db: Session, sensor_index: int) -> UserBiometric | None:
        stmt = select(UserBiometric).where(UserBiometric.sensor_index == sensor_index)
        return db.scalars(stmt).first()

    def get_manager_with_biometric(self, db: Session) -> User | None:
        stmt = (
            select(User)
            .join(UserBiometric)
            .where(
                User.role.in_([UserRole.MANAGER, UserRole.MAINTAINER]),
                User.is_active == True,
            )
        )
        return db.scalars(stmt).first()


device_credential_repository = DeviceCredentialRepository()
firmware_repository = FirmwareRepository()
biometric_repository = BiometricRepository()
