import pytz
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.core.config import settings
from app.domain.models.enums import RecordType
from app.schemas.mqtt import (
    DevicePunchRequest, FeedbackPayload, DeviceActions, EnrollResultPayload,
    BiometricSyncData, BiometricSyncAck, TimeResponsePayload
)
from app.services.biometric_service import biometric_service
from app.services.punch_service import punch_service

router = APIRouter()


@router.post("/punch", response_model=FeedbackPayload)
def register_device_punch(
        payload: DevicePunchRequest,
        db: Session = Depends(deps.get_db),
        api_key: str = Depends(deps.verify_api_key)
):
    try:
        success, message, record = punch_service.process_biometric_punch(db, payload.sensor_index)

        if success and record:
            user_first_name = record.user.name.split()[0] if record.user.name else "Usuario"
            time_formatted = record.record_datetime.strftime('%H:%M')
            type_label = "Entrada" if record.record_type == RecordType.ENTRY else "Saida"

            return FeedbackPayload(
                line1=f"Ola, {user_first_name[:11]}",
                line2=f"{type_label} {time_formatted}",
                led="green",
                actions=DeviceActions(
                    buzzer_pattern=1, buzzer_duration_ms=500
                )
            )
        else:
            return FeedbackPayload(
                line1="Erro",
                line2=message[:16],
                led="red",
                actions=DeviceActions(
                    buzzer_pattern=2, buzzer_duration_ms=1000
                )
            )
    except Exception as e:
        return FeedbackPayload(
            line1="Erro Interno",
            line2="Contate Admin",
            led="red",
            actions=DeviceActions(
                buzzer_pattern=2, buzzer_duration_ms=1000
            )
        )


@router.post("/enroll", response_model=FeedbackPayload)
def enroll_device_biometric(
        payload: EnrollResultPayload,
        db: Session = Depends(deps.get_db),
        api_key: str = Depends(deps.verify_api_key)
):
    try:
        success, msg = biometric_service.save_enrolled_biometric(db, payload)

        if success:
            return FeedbackPayload(
                line1="Cadastro OK",
                line2=f"ID: {payload.sensor_index}",
                led="green",
                actions=DeviceActions(
                    buzzer_pattern=1, buzzer_duration_ms=500
                )
            )
        else:
            return FeedbackPayload(
                line1="Erro Cadastro",
                line2=msg[:16],
                led="red",
                actions=DeviceActions(
                    buzzer_pattern=2, buzzer_duration_ms=1000
                )
            )
    except Exception as e:
        return FeedbackPayload(
            line1="Erro Interno",
            line2="Contate Admin",
            led="red",
            actions=DeviceActions(
                buzzer_pattern=2, buzzer_duration_ms=1000
            )
        )


@router.get("/sync", response_model=List[BiometricSyncData])
def sync_device_data(
        db: Session = Depends(deps.get_db),
        api_key: str = Depends(deps.verify_api_key)
):
    return biometric_service.get_all_for_sync(db)


@router.post("/sync/ack", status_code=200)
def sync_device_ack(
        payload: BiometricSyncAck,
        db: Session = Depends(deps.get_db),
        api_key: str = Depends(deps.verify_api_key)
):
    biometric_service.process_sync_ack(db, payload)
    return {"status": "success"}


@router.get("/time", response_model=TimeResponsePayload)
def get_device_time(
        api_key: str = Depends(deps.verify_api_key)
):
    tz = pytz.timezone(settings.TIMEZONE)
    now = datetime.now(tz)
    return TimeResponsePayload(
        unix=int(now.timestamp()),
        formatted=now.strftime("%d/%m/%Y %H:%M:%S")
    )
