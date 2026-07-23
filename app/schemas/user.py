import re
from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, field_validator, EmailStr, ConfigDict, Field

from app.domain.models.enums import UserRole
from app.schemas.biometric import UserBiometricCreate, UserBiometricUpdate, UserBiometricResponse
from app.schemas.work_schedule import WorkScheduleCreate, WorkSchedule


def validate_cpf_logic(cpf: str) -> bool:
    cpf = re.sub(r'[^0-9]', '', cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        val = sum((int(cpf[num]) * ((i + 1) - num) for num in range(0, i)))
        digit = ((val * 10) % 11) % 10
        if digit != int(cpf[i]):
            return False
    return True


class UserBase(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    cpf: Optional[str] = None
    pis: Optional[str] = None
    endereco: Optional[str] = None
    data_nascimento: Optional[date] = None
    role: Optional[UserRole] = UserRole.EMPLOYEE
    is_active: Optional[bool] = True
    can_manual_punch_desktop: Optional[bool] = True
    can_manual_punch_mobile: Optional[bool] = False
    can_export_report: Optional[bool] = False
    is_exempt_from_rules: Optional[bool] = False
    is_tolerance_exempt: Optional[bool] = False

    @field_validator('username')
    @classmethod
    def username_to_lower(cls, v: str | None) -> str | None:
        if v:
            return v.lower()
        return v

    @field_validator('cpf')
    @classmethod
    def validate_cpf(cls, v: str | None) -> str | None:
        if v:
            v_clean = re.sub(r'[^0-9]', '', v)
            if not validate_cpf_logic(v_clean):
                raise ValueError('CPF inválido')
            return v_clean
        return v


class UserCreate(UserBase):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.EMPLOYEE
    biometrics: List[UserBiometricCreate] = []

    @field_validator('data_nascimento')
    @classmethod
    def validate_data_nascimento(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError('A data de nascimento não pode estar no futuro.')
        return v


class UserUpdate(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    cpf: Optional[str] = None
    pis: Optional[str] = None
    endereco: Optional[str] = None
    data_nascimento: Optional[date] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    can_manual_punch_desktop: Optional[bool] = None
    can_manual_punch_mobile: Optional[bool] = None
    can_export_report: Optional[bool] = None
    is_exempt_from_rules: Optional[bool] = None
    is_tolerance_exempt: Optional[bool] = None
    schedules: Optional[List[WorkScheduleCreate]] = None
    biometrics: Optional[List[UserBiometricUpdate]] = None

    @field_validator('username')
    @classmethod
    def username_to_lower(cls, v: str | None) -> str | None:
        if v:
            return v.lower()
        return v

    @field_validator('cpf')
    @classmethod
    def validate_cpf(cls, v: str | None) -> str | None:
        if v:
            v_clean = re.sub(r'[^0-9]', '', v)
            if not validate_cpf_logic(v_clean):
                raise ValueError('CPF inválido')
            return v_clean
        return v

    @field_validator('data_nascimento')
    @classmethod
    def validate_data_nascimento(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError('A data de nascimento não pode estar no futuro.')
        return v


class UserUpdateMe(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    endereco: Optional[str] = None
    data_nascimento: Optional[date] = None

    @field_validator('data_nascimento')
    @classmethod
    def validate_data_nascimento(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError('A data de nascimento não pode estar no futuro.')
        return v


class UserInDBBase(UserBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class User(UserInDBBase):
    pass


class UserResponse(UserInDBBase):
    schedules: List[WorkSchedule] = Field(default_factory=list, validation_alias="current_schedules")
    biometrics: List[UserBiometricResponse] = []
