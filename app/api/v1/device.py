from typing import Annotated

from app.api import deps
from app.api.openapi_responses import UNAUTHORIZED_RESPONSE
from app.core.security import get_client_ip
from app.domain.models.device import DeviceCredential
from app.schemas.device import (
    DevicePunchRequest,
    FeedbackPayload,
    ManagerVerifyRequest,
    ManagerVerifyResponse,
    TimeResponsePayload,
)
from app.services.device_service import device_service
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.post("/punch", dependencies=[Depends(deps.verify_device_api_key)])
def register_device_punch(
        payload: DevicePunchRequest,
        request: Request,
        db: Annotated[Session, Depends(deps.get_db)],
) -> FeedbackPayload:
    ip_address = get_client_ip(request)
    return device_service.process_punch(
        db=db,
        sensor_index=payload.sensor_index,
        ip_address=ip_address,
        request=request,
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
