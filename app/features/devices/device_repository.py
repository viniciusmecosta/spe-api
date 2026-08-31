from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.security import get_api_key_hash
from app.database.repository import AsyncBaseRepository, BaseRepository
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
            self, db: Session, *, db_obj: DeviceCredential, obj_in: DeviceCredentialUpdate | dict[str, Any]
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


class AsyncDeviceCredentialRepository(
    AsyncBaseRepository[DeviceCredential, DeviceCredentialCreate, DeviceCredentialUpdate]):
    def __init__(self):
        super().__init__(DeviceCredential)

    async def create(self, db: AsyncSession, *, obj_in: DeviceCredentialCreate) -> DeviceCredential:
        hashed_key = get_api_key_hash(obj_in.api_key)
        db_obj = DeviceCredential(
            name=obj_in.name,
            key_type=obj_in.key_type,
            api_key_hash=hashed_key,
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get(self, db: AsyncSession, id: int) -> DeviceCredential | None:
        return await super().get(db, id)

    async def get_all(self, db: AsyncSession) -> list[DeviceCredential]:
        stmt = select(DeviceCredential)
        result = await db.scalars(stmt)
        return list(result.all())

    async def update(
            self, db: AsyncSession, *, db_obj: DeviceCredential, obj_in: DeviceCredentialUpdate | dict[str, Any]
    ) -> DeviceCredential:
        return await super().update(db, db_obj=db_obj, obj_in=obj_in)

    async def delete(self, db: AsyncSession, id: int):
        await super().remove(db, id=id)


class AsyncFirmwareRepository(AsyncBaseRepository[Firmware, Firmware, Firmware]):
    def __init__(self):
        super().__init__(Firmware)

    async def get_by_version(self, db: AsyncSession, version: str) -> Firmware | None:
        stmt = (
            select(Firmware)
            .where(Firmware.version == version)
            .order_by(desc(Firmware.created_at))
        )
        result = await db.scalars(stmt)
        return result.first()

    async def get_latest(self, db: AsyncSession) -> Firmware | None:
        stmt = select(Firmware).order_by(desc(Firmware.created_at))
        result = await db.scalars(stmt)
        return result.first()

    async def get_all(self, db: AsyncSession) -> list[Firmware]:
        stmt = select(Firmware).order_by(desc(Firmware.created_at))
        result = await db.scalars(stmt)
        return list(result.all())

    async def create(
            self,
            db: AsyncSession,
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
        await db.commit()
        await db.refresh(db_obj)
        return db_obj


class AsyncBiometricRepository(AsyncBaseRepository[UserBiometric, UserBiometric, UserBiometric]):
    def __init__(self):
        super().__init__(UserBiometric)

    async def get_by_sensor_index(self, db: AsyncSession, sensor_index: int) -> UserBiometric | None:
        from sqlalchemy.orm import selectinload
        stmt = (
            select(UserBiometric)
            .options(selectinload(UserBiometric.user))
            .where(UserBiometric.sensor_index == sensor_index)
        )
        result = await db.scalars(stmt)
        return result.first()

    async def get_manager_with_biometric(self, db: AsyncSession) -> User | None:
        stmt = (
            select(User)
            .join(UserBiometric)
            .where(
                User.role.in_([UserRole.MANAGER, UserRole.MAINTAINER]),
                User.is_active == True,
            )
        )
        result = await db.scalars(stmt)
        return result.first()


device_credential_repository = DeviceCredentialRepository()
firmware_repository = FirmwareRepository()
biometric_repository = BiometricRepository()

async_device_credential_repository = AsyncDeviceCredentialRepository()
async_firmware_repository = AsyncFirmwareRepository()
async_biometric_repository = AsyncBiometricRepository()
