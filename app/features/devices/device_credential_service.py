from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_repository import device_credential_repository
from app.features.devices.device_schemas import (
    DeviceCredentialCreate,
    DeviceCredentialUpdate,
)
from app.features.system.audit_service import audit_service


class DeviceCredentialService:
    def create(
            self,
            db: Session,
            credential_in: DeviceCredentialCreate,
            current_user_id: int,
    ) -> DeviceCredential:
        device = device_credential_repository.create(db, credential_in)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="CREATE",
            entity="DEVICE_CREDENTIAL",
            entity_id=device.id,
            new_data={"name": device.name, "key_type": device.key_type.value},
        )
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credencial não encontrada.",
            )

        old_data = {"name": device.name, "is_active": device.is_active}

        updated_device = device_credential_repository.update(db, device, credential_in)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="UPDATE",
            entity="DEVICE_CREDENTIAL",
            entity_id=updated_device.id,
            old_data=old_data,
            new_data={"name": updated_device.name, "is_active": updated_device.is_active},
        )
        return updated_device

    def delete(
            self,
            db: Session,
            credential_id: int,
            current_user_id: int,
    ) -> dict[str, str]:
        device = device_credential_repository.get(db, credential_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credencial não encontrada.",
            )

        old_data = {"name": device.name}

        device_credential_repository.delete(db, credential_id)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="DELETE",
            entity="DEVICE_CREDENTIAL",
            entity_id=credential_id,
            old_data=old_data,
        )
        return {"status": "success"}


device_credential_service = DeviceCredentialService()
