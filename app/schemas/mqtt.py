from pydantic import BaseModel, Field

class PunchPayload(BaseModel):
    request_id: str = Field(..., description="UUID único da requisição para idempotência")
    sensor_index: int = Field(..., description="ID da biometria no sensor (0-127)")
    timestamp_device: int = Field(..., description="Timestamp Unix do momento do registro no dispositivo")