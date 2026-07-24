from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserBiometricBase(BaseModel):
    sensor_index: int | None = None
    template_data: str | None = None
    finger_id: int | None = Field(None, ge=0, le=9)


class UserBiometricCreate(UserBiometricBase):
    pass


class UserBiometricUpdate(BaseModel):
    id: int | None = None
    sensor_index: int | None = None
    template_data: str | None = None
    finger_id: int | None = Field(None, ge=0, le=9)


class UserBiometricResponse(UserBiometricBase):
    id: int
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
