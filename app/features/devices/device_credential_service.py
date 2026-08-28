from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.features.devices.device_exceptions import DeviceCredentialNotFoundError
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_repository import (
    AsyncDeviceCredentialRepository,
    async_device_credential_repository,
)
from app.features.devices.device_schemas import (
    DeviceCredentialCreate,
    DeviceCredentialUpdate,
)
from app.features.system.audit_service import audit_service, serialize_model


class DeviceCredentialService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(get_async_db)] = None,
            repo: Annotated[AsyncDeviceCredentialRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncDeviceCredentialRepository:
        return self._repo if self._repo is not None else async_device_credential_repository

    @repo.setter
    def repo(self, value: AsyncDeviceCredentialRepository) -> None:
        self._repo = value

    async def create(
            self,
            db: AsyncSession | None = None,
            credential_in: DeviceCredentialCreate | None = None,
            current_user_id: int = 0,
    ) -> DeviceCredential:
        session = db if db is not None else self.db
        assert session is not None
        assert credential_in is not None
        device = await self.repo.create(session, obj_in=credential_in)
        await audit_service.async_log_change(session, current_user_id, "CREATE", new_model=device)
        return device

    async def get_all(self, db: AsyncSession | None = None) -> list[DeviceCredential]:
        session = db if db is not None else self.db
        assert session is not None
        return await self.repo.get_all(session)

    async def update(
            self,
            db: AsyncSession | None = None,
            credential_id: int = 0,
            credential_in: DeviceCredentialUpdate | None = None,
            current_user_id: int = 0,
    ) -> DeviceCredential:
        session = db if db is not None else self.db
        assert session is not None
        assert credential_in is not None
        device = await self.repo.get(session, credential_id)
        if not device:
            raise DeviceCredentialNotFoundError(credential_id=credential_id)

        old_data = serialize_model(device)
        updated_device = await self.repo.update(session, db_obj=device, obj_in=credential_in)
        await audit_service.async_log_change(session, current_user_id, "UPDATE", old_model=old_data,
                                             new_model=updated_device)
        return updated_device

    async def delete(
            self,
            db: AsyncSession | None = None,
            credential_id: int = 0,
            current_user_id: int = 0,
    ) -> dict[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        device = await self.repo.get(session, credential_id)
        if not device:
            raise DeviceCredentialNotFoundError(credential_id=credential_id)

        old_data = serialize_model(device)
        await self.repo.delete(session, credential_id)
        await audit_service.async_log_change(session, current_user_id, "DELETE", old_model=old_data)
        return {"status": "success"}


device_credential_service = DeviceCredentialService()
