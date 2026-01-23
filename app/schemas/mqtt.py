from pydantic import BaseModel
from typing import Optional, Any


class DevicePunchRequest(BaseModel):
    sensor_index: int


class PunchPayload(BaseModel):
    request_id: Optional[str] = None
    sensor_index: int
    timestamp_device: Optional[int] = None
    biometric_id: Optional[int] = None
    user_id: Optional[int] = None


class DeviceActions(BaseModel):
    buzzer_pattern: int
    buzzer_duration_ms: int
    led_pattern: Optional[int] = None


class FeedbackPayload(BaseModel):
    request_id: Optional[str] = None
    line1: str
    line2: str
    actions: DeviceActions


class EnrollStartPayload(BaseModel):
    user_id: int
    user_name: str


class EnrollResultPayload(BaseModel):
    request_id: Optional[str] = None
    user_id: int
    sensor_index: int
    success: bool
    template_data: Optional[str] = None
    error: Optional[str] = None


class BiometricSyncData(BaseModel):
    biometric_id: int
    template_data: str
    user_id: int


class BiometricSyncAck(BaseModel):
    biometric_id: int
    sensor_index: int
    success: bool
    error: Optional[str] = None