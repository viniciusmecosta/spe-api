from typing import Optional
from pydantic import BaseModel, field_validator
from datetime import datetime
from app.domain.models.enums import UserRole

class UserBase(BaseModel):
    username: str
    name: str
    role: UserRole = UserRole.EMPLOYEE
    weekly_workload_hours: int = 44
    is_active: bool = True

    @field_validator('username')
    @classmethod
    def username_to_lower(cls, v: str) -> str:
        return v.lower()

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    weekly_workload_hours: Optional[int] = None

    @field_validator('username')
    @classmethod
    def username_to_lower(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.lower()
        return v

class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True