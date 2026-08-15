from datetime import datetime

from app.domain.models.enums import DeviceKeyType
from pydantic import BaseModel, ConfigDict


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


class TimeResponsePayload(BaseModel):
    unix: int
    formatted: str


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
