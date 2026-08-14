from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.device import (
    DeviceCredentialCreate,
    DeviceCredentialResponse,
    DeviceCredentialUpdate,
)
from app.services.device_credential_service import device_credential_service

router = APIRouter()


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def create_credential(
    credential_in: DeviceCredentialCreate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> DeviceCredentialResponse:
    return device_credential_service.create(db, credential_in, current_user.id)


@router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def list_credentials(
    db: Annotated[Session, Depends(deps.get_db)],
) -> list[DeviceCredentialResponse]:
    return device_credential_service.get_all(db)


@router.put(
    "/{id}",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Credencial não encontrada."},
    },
)
def update_credential(
    id: int,
    credential_in: DeviceCredentialUpdate,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> DeviceCredentialResponse:
    return device_credential_service.update(db, id, credential_in, current_user.id)


@router.delete(
    "/{id}",
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Credencial não encontrada."},
    },
)
def delete_credential(
    id: int,
    db: Annotated[Session, Depends(deps.get_db)],
    current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    return device_credential_service.delete(db, id, current_user.id)
