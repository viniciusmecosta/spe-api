from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.features.devices.device_exceptions import DeviceCredentialNotFoundError
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_repository import DeviceCredentialRepository, device_credential_repository
from app.features.devices.device_schemas import (
    DeviceCredentialCreate,
    DeviceCredentialUpdate,
)
from app.features.system.audit_service import audit_service, serialize_model
from app.shared import deps


class DeviceCredentialService:
    def __init__(
        self,
        db: Annotated[Session, Depends(deps.get_db)] = None,
        repo: Annotated[DeviceCredentialRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> DeviceCredentialRepository:
        return self._repo if self._repo is not None else device_credential_repository

    def create(
            self,
            db: Session | None = None,
            credential_in: DeviceCredentialCreate | None = None,
            current_user_id: int = 0,
    ) -> DeviceCredential:
        session = db if db is not None else self.db
        assert session is not None
        assert credential_in is not None
        device = self.repo.create(session, obj_in=credential_in)
        audit_service.log_change(session, current_user_id, "CREATE", new_model=device)
        return device

    def get_all(self, db: Session | None = None) -> list[DeviceCredential]:
        session = db if db is not None else self.db
        assert session is not None
        return self.repo.get_all(session)

    def update(
            self,
            db: Session | None = None,
            credential_id: int = 0,
            credential_in: DeviceCredentialUpdate | None = None,
            current_user_id: int = 0,
    ) -> DeviceCredential:
        session = db if db is not None else self.db
        assert session is not None
        assert credential_in is not None
        device = self.repo.get(session, credential_id)
        if not device:
            raise DeviceCredentialNotFoundError(credential_id=credential_id)

        old_data = serialize_model(device)
        updated_device = self.repo.update(session, db_obj=device, obj_in=credential_in)
        audit_service.log_change(session, current_user_id, "UPDATE", old_model=old_data, new_model=updated_device)
        return updated_device

    def delete(
            self,
            db: Session | None = None,
            credential_id: int = 0,
            current_user_id: int = 0,
    ) -> dict[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        device = self.repo.get(session, credential_id)
        if not device:
            raise DeviceCredentialNotFoundError(credential_id=credential_id)

        old_data = serialize_model(device)
        self.repo.delete(session, credential_id)
        audit_service.log_change(session, current_user_id, "DELETE", old_model=old_data)
        return {"status": "success"}


device_credential_service = DeviceCredentialService()
