from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class UserBiometricBase(BaseModel):
    sensor_index: Optional[int] = None
    template_data: Optional[str] = None
    description: Optional[str] = None
    finger_id: Optional[int] = Field(None, ge=0, le=9)


class UserBiometricCreate(UserBiometricBase):
    pass


class UserBiometricUpdate(BaseModel):
    id: Optional[int] = None
    sensor_index: Optional[int] = None
    template_data: Optional[str] = None
    description: Optional[str] = None
    finger_id: Optional[int] = Field(None, ge=0, le=9)


class UserBiometricResponse(UserBiometricBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
