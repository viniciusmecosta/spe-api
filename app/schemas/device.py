from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field

from app.domain.models.enums import DeviceKeyType


class DevicePunchResponse(BaseModel):
    message: Optional[str] = None
    led: str
    data: Optional[Any] = None


class DevicePunchRequest(BaseModel):
    sensor_index: int


class DeviceActions(BaseModel):
    buzzer_pattern: int
    buzzer_duration_ms: int


class FeedbackPayload(BaseModel):
    line1: str
    line2: str
    led: str
    actions: DeviceActions


class EnrollStartPayload(BaseModel):
    user_id: int
    user_name: str


class EnrollResultPayload(BaseModel):
    user_id: int
    sensor_index: int
    success: bool
    template_data: Optional[str] = None
    error: Optional[str] = None
    finger_id: Optional[int] = Field(None, ge=0, le=9)


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
    error: Optional[str] = None


class DeviceCredentialCreate(BaseModel):
    name: str
    device_id: str
    key_type: DeviceKeyType
    api_key: str
    is_active: bool = True


class DeviceCredentialUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class DeviceCredentialResponse(BaseModel):
    id: int
    device_id: str
    name: str
    key_type: DeviceKeyType
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
