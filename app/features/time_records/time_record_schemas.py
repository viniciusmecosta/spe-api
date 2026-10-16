from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.shared.timezone import to_app_timezone
from app.shared.enums import RecordType


class SuccessResponse(BaseModel):
    status: str = "success"
    message: str


class TimeRecordBase(BaseModel):
    record_type: RecordType
    record_datetime: datetime
    ip_address: str | None = None
    device_name: str | None = None
    platform: str | None = None
    biometric_id: int | None = None


class TimeRecordCreate(BaseModel):
    pass


class TimeRecordCreateAdmin(BaseModel):
    user_id: int
    record_type: RecordType
    record_datetime: datetime
    edit_justification: str = Field(..., max_length=300)

    @field_validator("record_datetime")
    @classmethod
    def normalize_record_timezone(cls, value: datetime) -> datetime:
        return to_app_timezone(value)


class TimeRecordUpdate(BaseModel):
    record_type: RecordType | None = None
    record_datetime: datetime | None = None
    edit_justification: str = Field(..., max_length=300)

    @field_validator("record_datetime")
    @classmethod
    def normalize_record_timezone(cls, value: datetime | None) -> datetime | None:
        return to_app_timezone(value) if value is not None else None


class TimeRecordDeleteAdmin(BaseModel):
    edit_justification: str = Field(..., max_length=300)


class TimeRecordSimple(BaseModel):
    record_type: RecordType
    record_datetime: datetime

    @field_validator("record_datetime")
    @classmethod
    def normalize_record_timezone(cls, value: datetime) -> datetime:
        return to_app_timezone(value)

    model_config = ConfigDict(from_attributes=True)


class TimeRecordResponse(TimeRecordBase):
    id: int
    short_id: str
    user_id: int
    created_at: datetime
    edited_by: str | None = Field(None, validation_alias=AliasChoices('editor_name', 'edited_by'))
    edit_justification: str | None = None
    original_record_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class TimeRecordTimelineResponse(TimeRecordResponse):
    is_ignored: bool
    model_config = ConfigDict(from_attributes=True)


class ReceiptTimelineItem(BaseModel):
    action: str | None = None
    timestamp: datetime | str | None = None
    user_name: str | None = None
    old_data: Any | None = None
    new_data: Any | None = None
    model_config = ConfigDict(from_attributes=True)


class ReceiptResponse(BaseModel):
    short_id: str
    record_id: int
    company_name: str
    company_cnpj: str
    company_address: str | None = None
    employee_name: str
    employee_cpf: str | None = None
    employee_pis: str | None = None
    record_datetime: datetime
    device_name: str
    record_type: RecordType
    timeline: list[ReceiptTimelineItem] = []
    model_config = ConfigDict(from_attributes=True)
