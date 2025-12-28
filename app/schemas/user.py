from typing import Optional, List
from pydantic import BaseModel, field_validator
from datetime import datetime
from app.domain.models.enums import UserRole
from app.schemas.work_schedule import WorkSchedule, WorkScheduleCreate

class UserBase(BaseModel):
    username: str
    name: str
    role: UserRole = UserRole.EMPLOYEE
    is_active: bool = True

    @field_validator('username')
    @classmethod
    def username_to_lower(cls, v: str) -> str:
        return v.lower()

class UserCreate(UserBase):
    password: str
    schedules: Optional[List[WorkScheduleCreate]] = []

class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    schedules: Optional[List[WorkScheduleCreate]] = None

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
    schedules: List[WorkSchedule] = []

    class Config:
        from_attributes = True