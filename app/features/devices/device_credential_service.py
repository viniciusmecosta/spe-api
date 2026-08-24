from sqlalchemy.orm import Session

from app.features.devices.device_exceptions import DeviceCredentialNotFoundError
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_repository import device_credential_repository
from app.features.devices.device_schemas import (
    DeviceCredentialCreate,
    DeviceCredentialUpdate,
)
from app.features.system.audit_service import audit_service, serialize_model


class DeviceCredentialService:
    def create(
            self,
            db: Session,
            credential_in: DeviceCredentialCreate,
            current_user_id: int,
    ) -> DeviceCredential:
        device = device_credential_repository.create(db, credential_in)
        audit_service.log_change(db, current_user_id, "CREATE", new_model=device)
        return device

    def get_all(self, db: Session) -> list[DeviceCredential]:
        return device_credential_repository.get_all(db)

    def update(
            self,
            db: Session,
            credential_id: int,
            credential_in: DeviceCredentialUpdate,
            current_user_id: int,
    ) -> DeviceCredential:
        device = device_credential_repository.get(db, credential_id)
        if not device:
            raise DeviceCredentialNotFoundError(credential_id=credential_id)

        old_data = serialize_model(device)
        updated_device = device_credential_repository.update(db, device, credential_in)
        audit_service.log_change(db, current_user_id, "UPDATE", old_model=old_data, new_model=updated_device)
        return updated_device

    def delete(
            self,
            db: Session,
            credential_id: int,
            current_user_id: int,
    ) -> dict[str, str]:
        device = device_credential_repository.get(db, credential_id)
        if not device:
            raise DeviceCredentialNotFoundError(credential_id=credential_id)

        device_credential_repository.delete(db, credential_id)
        audit_service.log_change(db, current_user_id, "DELETE", old_model=device)
        return {"status": "success"}


device_credential_service = DeviceCredentialService()
