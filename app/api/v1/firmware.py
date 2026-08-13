from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_maintainer, get_db, verify_device_api_key
from app.domain.models.user import User
from app.schemas.firmware import FirmwareListResponse, FirmwareResponse
from app.services.firmware_service import firmware_service

router = APIRouter()


@router.get(
    "/",
    dependencies=[Depends(get_current_maintainer)],
    responses={
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def list_firmwares(
    db: Annotated[Session, Depends(get_db)],
) -> list[FirmwareListResponse]:
    return firmware_service.get_all_firmwares(db)


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Arquivo inválido ou versão duplicada"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
    },
)
def upload_firmware(
    version: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_maintainer)],
) -> FirmwareResponse:
    return firmware_service.upload_firmware(db, version, file, current_user.id)


@router.put(
    "/{version}",
    responses={
        400: {"description": "Arquivo inválido"},
        401: {"description": "Não autenticado"},
        403: {"description": "Permissão insuficiente"},
        404: {"description": "Firmware não encontrado"},
    },
)
def update_firmware(
    version: str,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_maintainer)],
) -> FirmwareResponse:
    return firmware_service.update_firmware_file(db, version, file, current_user.id)


@router.get(
    "/check",
    dependencies=[Depends(verify_device_api_key)],
    responses={
        401: {"description": "Chave de dispositivo inválida"},
        404: {"description": "Nenhum firmware disponível"},
    },
)
def check_firmware(
    db: Annotated[Session, Depends(get_db)],
) -> FirmwareResponse:
    return firmware_service.get_latest_firmware(db)


@router.get(
    "/download",
    dependencies=[Depends(verify_device_api_key)],
    responses={
        401: {"description": "Chave de dispositivo inválida"},
        404: {"description": "Firmware não encontrado"},
    },
)
def download_firmware(
    version: str,
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    file_path = firmware_service.get_firmware_file(db, version)
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=f"firmware_{version}.bin",
    )
