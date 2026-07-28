import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.models.enums import UserRole
from app.schemas.biometric import (
    UserBiometricCreate,
    UserBiometricResponse,
    UserBiometricUpdate,
)
from app.schemas.work_schedule import WorkSchedule, WorkScheduleCreate

DOB_FUTURE_ERROR = 'A data de nascimento não pode estar no futuro.'


def validate_cpf_logic(cpf: str) -> bool:
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        val = sum(int(cpf[num]) * ((i + 1) - num) for num in range(i))
        digit = ((val * 10) % 11) % 10
        if digit != int(cpf[i]):
            return False
    return True


class UserBase(BaseModel):
    username: str | None = None
    name: str | None = None
    email: EmailStr | None = None
    cpf: str | None = None
    pis: str | None = None
    endereco: str | None = None
    data_nascimento: date | None = None
    role: UserRole | None = UserRole.EMPLOYEE
    is_active: bool | None = True
    can_manual_punch_desktop: bool | None = True
    can_manual_punch_mobile: bool | None = False
    can_export_report: bool | None = False
    is_exempt_from_rules: bool | None = False
    is_tolerance_exempt: bool | None = False

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
            v_clean = re.sub(r'\D', '', v)
            if not validate_cpf_logic(v_clean):
                raise ValueError('CPF inválido')
            return v_clean
        return v

    @field_validator('data_nascimento')
    @classmethod
    def validate_data_nascimento(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError(DOB_FUTURE_ERROR)
        return v


class UserCreate(UserBase):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.EMPLOYEE
    biometrics: list[UserBiometricCreate] = []


class UserUpdate(BaseModel):
    username: str | None = None
    name: str | None = None
    password: str | None = None
    email: EmailStr | None = None
    cpf: str | None = None
    pis: str | None = None
    endereco: str | None = None
    data_nascimento: date | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    can_manual_punch_desktop: bool | None = None
    can_manual_punch_mobile: bool | None = None
    can_export_report: bool | None = None
    is_exempt_from_rules: bool | None = None
    is_tolerance_exempt: bool | None = None
    biometrics: list[UserBiometricUpdate] | None = None

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
            v_clean = re.sub(r'\D', '', v)
            if not validate_cpf_logic(v_clean):
                raise ValueError('CPF inválido')
            return v_clean
        return v

    @field_validator('data_nascimento')
    @classmethod
    def validate_data_nascimento(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError(DOB_FUTURE_ERROR)
        return v


class UserUpdateMe(BaseModel):
    name: str | None = None
    password: str | None = None
    email: EmailStr | None = None
    endereco: str | None = None
    data_nascimento: date | None = None

    @field_validator('data_nascimento')
    @classmethod
    def validate_data_nascimento(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError(DOB_FUTURE_ERROR)
        return v


class UserInDBBase(UserBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class User(UserInDBBase):
    pass


class UserResponse(UserInDBBase):
    schedules: list[WorkSchedule] = Field(default_factory=list, validation_alias="current_schedules")
    biometrics: list[UserBiometricResponse] = []
