from pydantic import BaseModel
from typing import Optional, Any


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
