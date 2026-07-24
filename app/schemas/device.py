from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.enums import DeviceKeyType


class DevicePunchResponse(BaseModel):
    message: str | None = None
    led: str
    data: Any | None = None


class DevicePunchRequest(BaseModel):
    sensor_index: int


class BuzzerNote(BaseModel):
    frequency: int
    duration_ms: int


class DeviceActions(BaseModel):
    buzzer_melody: list[BuzzerNote]


class FeedbackPayload(BaseModel):
    line1: str
    line2: str
    line3: str
    led: str
    actions: DeviceActions


class EnrollStartPayload(BaseModel):
    user_id: int
    user_name: str


class EnrollResultPayload(BaseModel):
    user_id: int
    sensor_index: int
    success: bool
    template_data: str | None = None
    error: str | None = None
    finger_id: int | None = Field(None, ge=0, le=9)


class TimeResponsePayload(BaseModel):
    unix: int
    formatted: str


class BiometricSyncData(BaseModel):
    biometric_id: int
    template_data: str
    user_id: int


class BiometricSyncAck(BaseModel):
    biometric_id: int
    sensor_index: int
    success: bool
    error: str | None = None


class DeviceCredentialCreate(BaseModel):
    name: str
    key_type: DeviceKeyType
    api_key: str
    is_active: bool = True


class DeviceCredentialUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class DeviceCredentialResponse(BaseModel):
    id: int
    name: str
    key_type: DeviceKeyType
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManagerVerifyRequest(BaseModel):
    sensor_index: int


class ManagerVerifyResponse(BaseModel):
    is_allowed: bool
    message: str
