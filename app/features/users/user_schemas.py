import re
from datetime import date, datetime, time
from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Annotated, Any

from app.features.devices.device_schemas import (
    UserBiometricCreate,
    UserBiometricResponse,
    UserBiometricUpdate,
)
from app.shared.enums import UserRole

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


def _validate_cpf_val(v: str | None) -> str | None:
    if v:
        v_clean = re.sub(r'\D', '', v)
        if not validate_cpf_logic(v_clean):
            raise ValueError('CPF inválido')
        return v_clean
    return v


def _username_to_lower(v: str | None) -> str | None:
    if v:
        return v.lower()
    return v


def _validate_dob(v: date | None) -> date | None:
    if v and v > date.today():
        raise ValueError(DOB_FUTURE_ERROR)
    return v


CpfStr = Annotated[str | None, AfterValidator(_validate_cpf_val)]
UsernameLowerStr = Annotated[str | None, AfterValidator(_username_to_lower)]
PastDate = Annotated[date | None, AfterValidator(_validate_dob)]


class WorkScheduleBase(BaseModel):
    day_of_week: int
    daily_hours: float
    entry_1: time | None = None
    exit_1: time | None = None
    entry_2: time | None = None
    exit_2: time | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    is_daily_excess_enabled: bool | None = True


class WorkSchedule(WorkScheduleBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class UserScheduleInput(BaseModel):
    user_id: int
    schedules: list[WorkScheduleBase]


class BulkWorkScheduleCreate(BaseModel):
    valid_from: date
    valid_until: date
    users: list[UserScheduleInput]


class BulkWorkScheduleResponse(BaseModel):
    valid_from: date
    valid_until: date
    users: list[UserScheduleInput]


class UserBase(BaseModel):
    username: UsernameLowerStr = None
    name: str | None = None
    email: EmailStr | None = None
    cpf: CpfStr = None
    pis: str | None = None
    endereco: str | None = None
    data_nascimento: PastDate = None
    role: UserRole | None = UserRole.EMPLOYEE
    is_active: bool = True
    can_manual_punch_desktop: bool = True
    can_manual_punch_mobile: bool = False
    can_export_report: bool = False
    is_exempt_from_rules: bool = False
    is_tolerance_exempt: bool = False
    auto_print_receipt: bool | None = None


class UserCreate(UserBase):
    username: Annotated[str, Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$"), AfterValidator(_username_to_lower)]
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.EMPLOYEE
    biometrics: list[UserBiometricCreate] = []


class UserUpdate(BaseModel):
    username: UsernameLowerStr = None
    name: str | None = None
    password: str | None = None
    email: EmailStr | None = None
    cpf: CpfStr = None
    pis: str | None = None
    endereco: str | None = None
    data_nascimento: PastDate = None
    role: UserRole | None = None
    is_active: bool | None = None
    can_manual_punch_desktop: bool | None = None
    can_manual_punch_mobile: bool | None = None
    can_export_report: bool | None = None
    is_exempt_from_rules: bool | None = None
    is_tolerance_exempt: bool | None = None
    auto_print_receipt: bool | None = None
    biometrics: list[UserBiometricUpdate] | None = None

    @field_validator(
        "is_active",
        "can_manual_punch_desktop",
        "can_manual_punch_mobile",
        "can_export_report",
        "is_exempt_from_rules",
        "is_tolerance_exempt",
        mode="before",
    )
    @classmethod
    def reject_null_required_flags(cls, value: bool | None) -> bool | None:
        if value is None:
            raise ValueError("Este campo booleano não pode ser nulo.")
        return value


class UserUpdateMe(BaseModel):
    name: str | None = None
    password: str | None = None
    email: EmailStr | None = None
    endereco: str | None = None
    data_nascimento: PastDate = None


class UserInDBBase(UserBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "is_active",
        "can_manual_punch_desktop",
        "can_manual_punch_mobile",
        "can_export_report",
        "is_exempt_from_rules",
        "is_tolerance_exempt",
        mode="before",
    )
    @classmethod
    def set_boolean_defaults(cls, value: Any, info) -> Any:
        if value is None:
            defaults = {
                "is_active": True,
                "can_manual_punch_desktop": True,
                "can_manual_punch_mobile": False,
                "can_export_report": False,
                "is_exempt_from_rules": False,
                "is_tolerance_exempt": False,
            }
            return defaults.get(info.field_name, False)
        return value


class User(UserInDBBase):
    pass


class UserResponse(UserInDBBase):
    schedules: list[WorkSchedule] = Field(default_factory=list, validation_alias="current_schedules")
    biometrics: list[UserBiometricResponse] = []
