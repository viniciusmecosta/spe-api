from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.repositories.device_credential_repository import device_credential_repository
from app.schemas.device import DeviceCredentialCreate, DeviceCredentialUpdate, DeviceCredentialResponse
from app.services.audit_service import audit_service

router = APIRouter()


@router.post("/", response_model=DeviceCredentialResponse)
def create_credential(
        credential_in: DeviceCredentialCreate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    device = device_credential_repository.create(db, credential_in)

    audit_service.log(
        db, actor_id=current_user.id, action="CREATE", entity="DEVICE_CREDENTIAL",
        entity_id=device.id,
        new_data={"name": device.name, "key_type": device.key_type.value}
    )
    return device


@router.get("/", response_model=List[DeviceCredentialResponse])
def list_credentials(
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    return device_credential_repository.get_all(db)


@router.put("/{id}", response_model=DeviceCredentialResponse)
def update_credential(
        id: int,
        credential_in: DeviceCredentialUpdate,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    device = device_credential_repository.get(db, id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial não encontrada.")

    old_data = {"name": device.name, "is_active": device.is_active}

    updated_device = device_credential_repository.update(db, device, credential_in)

    audit_service.log(
        db, actor_id=current_user.id, action="UPDATE", entity="DEVICE_CREDENTIAL",
        entity_id=updated_device.id, old_data=old_data,
        new_data={"name": updated_device.name, "is_active": updated_device.is_active}
    )
    return updated_device


@router.delete("/{id}")
def delete_credential(
        id: int,
        db: Session = Depends(deps.get_db),
        current_user: User = Depends(deps.get_current_maintainer)
):
    device = device_credential_repository.get(db, id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial não encontrada.")

    old_data = {"name": device.name}

    device_credential_repository.delete(db, id)

    audit_service.log(
        db, actor_id=current_user.id, action="DELETE", entity="DEVICE_CREDENTIAL",
        entity_id=id, old_data=old_data
    )
    return {"status": "success"}