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

from app.core.security import get_client_ip
from app.features.devices.biometric_service import BiometricService
from app.features.devices.device_credential_service import (
    DeviceCredentialService,
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
from app.features.devices.device_service import DeviceService
from app.features.devices.firmware_service import FirmwareService
from app.features.devices.sync_service import SyncService
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


@router.post("/punch", dependencies=[Depends(deps.verify_device_api_key)])
async def register_device_punch(
        payload: DevicePunchRequest,
        request: Request,
        background_tasks: BackgroundTasks,
        device_service: Annotated[DeviceService, Depends()],
) -> FeedbackPayload:
    ip_address = get_client_ip(request)
    return await device_service.process_punch(
        sensor_index=payload.sensor_index,
        ip_address=ip_address,
        request=request,
        background_tasks=background_tasks,
    )


@router.get("/time", dependencies=[Depends(deps.verify_device_api_key)])
async def get_device_time(
        device_service: Annotated[DeviceService, Depends()],
) -> TimeResponsePayload:
    return device_service.get_device_time()


@router.post("/verify-manager")
async def verify_manager_access(
        payload: ManagerVerifyRequest,
        device: Annotated[DeviceCredential, Depends(deps.verify_device_api_key)],
        device_service: Annotated[DeviceService, Depends()],
) -> ManagerVerifyResponse:
    return await device_service.verify_manager_access(
        sensor_index=payload.sensor_index,
        device_id=device.id,
    )


@device_credentials_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
        credential_in: DeviceCredentialCreate,
        device_credential_service: Annotated[DeviceCredentialService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> DeviceCredentialResponse:
    return await device_credential_service.create(credential_in=credential_in, current_user_id=current_user.id)


@device_credentials_router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
)
async def list_credentials(
        device_credential_service: Annotated[DeviceCredentialService, Depends()],
) -> list[DeviceCredentialResponse]:
    return await device_credential_service.get_all()


@device_credentials_router.put(
    "/{id}",
    responses={**CRUD_RESPONSES},
)
async def update_credential(
        id: int,
        credential_in: DeviceCredentialUpdate,
        device_credential_service: Annotated[DeviceCredentialService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> DeviceCredentialResponse:
    return await device_credential_service.update(credential_id=id, credential_in=credential_in,
                                                  current_user_id=current_user.id)


@device_credentials_router.delete(
    "/{id}",
    responses={**CRUD_RESPONSES},
)
async def delete_credential(
        id: int,
        device_credential_service: Annotated[DeviceCredentialService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> dict[str, str]:
    return await device_credential_service.delete(credential_id=id, current_user_id=current_user.id)


@firmware_router.get(
    "/",
    dependencies=[Depends(deps.get_current_maintainer)],
    responses={**AUTH_RESPONSES},
)
async def list_firmwares(
        firmware_service: Annotated[FirmwareService, Depends()],
) -> list[FirmwareListResponse]:
    return await firmware_service.get_all_firmwares()


@firmware_router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **AUTH_RESPONSES},
)
async def upload_firmware(
        version: Annotated[str, Form(...)],
        file: Annotated[UploadFile, File(...)],
        firmware_service: Annotated[FirmwareService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> FirmwareResponse:
    return await firmware_service.upload_firmware(version=version, file=file, current_user_id=current_user.id)


@firmware_router.put(
    "/{version}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def update_firmware(
        version: str,
        file: Annotated[UploadFile, File(...)],
        firmware_service: Annotated[FirmwareService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_maintainer)],
) -> FirmwareResponse:
    return await firmware_service.update_firmware_file(version=version, file=file, current_user_id=current_user.id)


@firmware_router.get(
    "/check",
    dependencies=[Depends(deps.verify_device_api_key)],
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def check_firmware(
        firmware_service: Annotated[FirmwareService, Depends()],
) -> FirmwareResponse:
    return await firmware_service.get_latest_firmware()


@firmware_router.get(
    "/download",
    dependencies=[Depends(deps.verify_device_api_key)],
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def download_firmware(
        version: str,
        firmware_service: Annotated[FirmwareService, Depends()],
) -> FileResponse:
    file_path = await firmware_service.get_firmware_file(version=version)
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=f"firmware_{version}.bin",
    )


@biometrics_router.get(
    "/available-sensor-indices",
    dependencies=[Depends(deps.get_current_manager)],
)
async def get_available_sensor_indices(
        biometric_service: Annotated[BiometricService, Depends()],
) -> list[int]:
    return await biometric_service.get_available_sensor_indices()


@sync_router.post(
    "/database",
    dependencies=[Depends(deps.verify_consumer_api_key)],
    responses={**BAD_REQUEST_RESPONSE, **UNAUTHORIZED_RESPONSE},
)
async def sync_database(
        file: Annotated[UploadFile, File(...)],
        sync_service: Annotated[SyncService, Depends()],
) -> dict[str, str]:
    sync_service.receive_database(file)
    return {"status": "success"}
