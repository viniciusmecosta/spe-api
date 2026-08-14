from typing import Annotated

from app.api.deps import get_current_maintainer, get_db, verify_device_api_key
from app.api.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from app.domain.models.user import User
from app.schemas.firmware import FirmwareListResponse, FirmwareResponse
from app.services.firmware_service import firmware_service
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

router = APIRouter()


@router.get(
    "/",
    dependencies=[Depends(get_current_maintainer)],
    responses={**AUTH_RESPONSES},
)
def list_firmwares(
        db: Annotated[Session, Depends(get_db)],
) -> list[FirmwareListResponse]:
    return firmware_service.get_all_firmwares(db)


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **AUTH_RESPONSES},
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
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
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
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
)
def check_firmware(
        db: Annotated[Session, Depends(get_db)],
) -> FirmwareResponse:
    return firmware_service.get_latest_firmware(db)


@router.get(
    "/download",
    dependencies=[Depends(verify_device_api_key)],
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
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
