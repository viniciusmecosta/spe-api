from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.domain.models.enums import UserRole


class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = True
    is_superuser: bool = False
    full_name: Optional[str] = None
    role: Optional[UserRole] = UserRole.EMPLOYEE


class UserCreate(UserBase):
    email: EmailStr
    password: str
    role: UserRole = UserRole.EMPLOYEE


class UserUpdate(UserBase):
    password: Optional[str] = None


class UserInDBBase(UserBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class User(UserInDBBase):
    pass


class UserResponse(UserInDBBase):
    can_manual_punch: bool = False
