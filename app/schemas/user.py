from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, field_validator

from app.domain.models.enums import UserRole
from app.schemas.work_schedule import WorkScheduleCreate


class UserBase(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    role: Optional[UserRole] = UserRole.EMPLOYEE
    is_active: Optional[bool] = True
    can_manual_punch: Optional[bool] = True

    @field_validator('username')
    @classmethod
    def username_to_lower(cls, v: str) -> str:
        return v.lower()


class UserCreate(UserBase):
    username: str
    password: str
    role: UserRole = UserRole.EMPLOYEE
    schedules: List[WorkScheduleCreate] = []


class UserUpdate(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    can_manual_punch: Optional[bool] = None
    schedules: Optional[List[WorkScheduleCreate]] = None

    @field_validator('username')
    @classmethod
    def username_to_lower(cls, v: str | None) -> str | None:
        if v:
            return v.lower()
        return v


class UserInDBBase(UserBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class User(UserInDBBase):
    pass


class UserResponse(UserInDBBase):
    pass
