from datetime import datetime

from pydantic import BaseModel, Field


class ManualPunchAuthCreate(BaseModel):
    user_id: int
    valid_from: datetime
    valid_until: datetime
    reason: str = Field(..., min_length=5, description="Motivo obrigatório para liberação manual")


class ManualPunchAuthResponse(ManualPunchAuthCreate):
    id: int
    authorized_by: int

    class Config:
        from_attributes = True
