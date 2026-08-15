from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import get_client_ip
from app.features.devices.biometric_service import biometric_service
from app.features.devices.device_credential_service import (
    device_credential_service,
)
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_schemas import (
    DeviceCredentialCreate,
    DeviceCredentialResponse,
    DeviceCredentialUpdate,
    DevicePunchRequest,
    FeedbackPayload,
    FirmwareListResponse,
    FirmwareResponse,
    ManagerVerifyRequest,
    ManagerVerifyResponse,
    TimeResponsePayload,
)
from app.features.devices.device_service import device_service
from app.features.devices.firmware_service import firmware_service
from app.features.devices.sync_service import sync_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.openapi_responses import (
    AUTH_RESPONSES,
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})
device_credentials_router = APIRouter(responses={**AUTH_RESPONSES})
firmware_router = APIRouter()
biometrics_router = APIRouter(responses={**AUTH_RESPONSES})
sync_router = APIRouter()


# --- Device endpoints ---
@router.post("/punch", dependencies=[Depends(deps.verify_device_api_key)])
def register_device_punch(
        payload: DevicePunchRequest,
        request: Request,
        background_tasks: BackgroundTasks,
        db: Annotated[Session, Depends(deps.get_db)],
) -> FeedbackPayload:
    ip_address = get_client_ip(request)
    return device_service.process_punch(
        db=db,
        sensor_index=payload.sensor_index,
        ip_address=ip_address,
        request=request,
        background_tasks=background_tasks,
    )


@router.get("/time", dependencies=[Depends(deps.verify_device_api_key)])
def get_device_time() -> TimeResponsePayload:
    return device_service.get_device_time()


@router.post("/verify-manager")
def verify_manager_access(
        payload: ManagerVerifyRequest,
        db: Annotated[Session, Depends(deps.get_db)],
        device: Annotated[DeviceCredential, Depends(deps.verify_device_api_key)],
) -> ManagerVerifyResponse:
    return device_service.verify_manager_access(
        db=db,
        sensor_index=payload.sensor_index,
        device_id=device.id,
    )


# --- Device Credentials endpoints ---
@device_credentials_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
)
def create_credential(
        credential_in: DeviceCredentialCreate,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> DeviceCredentialResponse:
    return device_credential_service.create(db, credential_in, current_user.id)


@device_credentials_router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
)
def list_credentials(
        db: Annotated[Session, Depends(deps.get_db)],
) -> list[DeviceCredentialResponse]:
    return device_credential_service.get_all(db)


@device_credentials_router.put(
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


@device_credentials_router.delete(
    "/{id}",
    responses={**CRUD_RESPONSES},
)
def delete_credential(
        id: int,
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    return device_credential_service.delete(db, id, current_user.id)


# --- Firmware endpoints ---
@firmware_router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**AUTH_RESPONSES},
)
def list_firmwares(
        db: Annotated[Session, Depends(deps.get_db)],
) -> list[FirmwareListResponse]:
    return firmware_service.get_all_firmwares(db)


@firmware_router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **AUTH_RESPONSES},
)
def upload_firmware(
        version: Annotated[str, Form(...)],
        file: Annotated[UploadFile, File(...)],
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> FirmwareResponse:
    return firmware_service.upload_firmware(db, version, file, current_user.id)


@firmware_router.put(
    "/{version}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
def update_firmware(
        version: str,
        file: Annotated[UploadFile, File(...)],
        db: Annotated[Session, Depends(deps.get_db)],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> FirmwareResponse:
    return firmware_service.update_firmware_file(db, version, file, current_user.id)


@firmware_router.get(
    "/check",
    dependencies=[Depends(deps.verify_device_api_key)],
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
)
def check_firmware(
        db: Annotated[Session, Depends(deps.get_db)],
) -> FirmwareResponse:
    return firmware_service.get_latest_firmware(db)


@firmware_router.get(
    "/download",
    dependencies=[Depends(deps.verify_device_api_key)],
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
)
def download_firmware(
        version: str,
        db: Annotated[Session, Depends(deps.get_db)],
) -> FileResponse:
    file_path = firmware_service.get_firmware_file(db, version)
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=f"firmware_{version}.bin",
    )


# --- Biometrics endpoints ---
@biometrics_router.get(
    "/available-sensor-indices",
    dependencies=[Depends(deps.get_current_manager)],
)
def get_available_sensor_indices(
        db: Annotated[Session, Depends(deps.get_db)],
) -> list[int]:
    return biometric_service.get_available_sensor_indices(db)


# --- Sync endpoints ---
@sync_router.post(
    "/database",
    dependencies=[Depends(deps.verify_consumer_api_key)],
    responses={**BAD_REQUEST_RESPONSE, **UNAUTHORIZED_RESPONSE},
)
def sync_database(
        file: Annotated[UploadFile, File(...)],
) -> dict[str, str]:
    sync_service.receive_database(file)
    return {"status": "success"}
