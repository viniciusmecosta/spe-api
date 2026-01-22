from pydantic import BaseModel
from typing import Optional, List


class PunchPayload(BaseModel):
    request_id: str
    sensor_index: int
    timestamp_device: int


class DeviceActions(BaseModel):
    buzzer_pattern: int
    buzzer_duration_ms: int


class FeedbackPayload(BaseModel):
    request_id: str
    line1: str
    line2: str
    actions: DeviceActions


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


class EnrollStartPayload(BaseModel):
    user_id: int
    user_name: str


class EnrollResultPayload(BaseModel):
    user_id: int
    sensor_index: int
    template_data: str
    success: bool
    error: Optional[str] = None