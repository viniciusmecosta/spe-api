from pydantic import BaseModel, Field

class PunchPayload(BaseModel):
    request_id: str = Field(..., description="UUID único da requisição para idempotência")
    sensor_index: int = Field(..., description="ID da biometria no sensor (0-127)")
    timestamp_device: int = Field(..., description="Timestamp Unix do momento do registro no dispositivo")

class DeviceActions(BaseModel):
    led_color: str = Field(..., pattern="^(green|red|off)$")
    led_duration_ms: int
    buzzer_pattern: int
    buzzer_duration_ms: int

class FeedbackPayload(BaseModel):
    request_id: str
    line1: str = Field(..., max_length=16)
    line2: str = Field(..., max_length=16)
    actions: DeviceActions

class TimeResponsePayload(BaseModel):
    unix: int
    formatted: str