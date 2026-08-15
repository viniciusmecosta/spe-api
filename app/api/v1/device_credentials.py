from typing import Annotated

from app.api import deps
from app.api.openapi_responses import AUTH_RESPONSES, CRUD_RESPONSES
from app.domain.models.user import User
from app.schemas.device import (
    DeviceCredentialCreate,
    DeviceCredentialResponse,
    DeviceCredentialUpdate,
)
from app.services.device_credential_service import device_credential_service
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

router = APIRouter(responses={**AUTH_RESPONSES})


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
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
)
def list_credentials(
        db: Annotated[Session, Depends(deps.get_db)],
) -> list[DeviceCredentialResponse]:
    return device_credential_service.get_all(db)


@router.put(
    "/{id}",
    responses={**CRUD_RESPONSES},
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
    responses={**CRUD_RESPONSES},
)
def delete_credential(
        id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    return device_credential_service.delete(db, id, current_user.id)
