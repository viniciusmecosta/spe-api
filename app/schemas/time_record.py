from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.domain.models.enums import RecordType


class SuccessResponse(BaseModel):
    status: str = "success"
    message: str

class TimeRecordBase(BaseModel):
    record_type: RecordType
    record_datetime: datetime
    ip_address: str | None = None
    device_name: str | None = None
    platform: str | None = None

class TimeRecordCreate(BaseModel):
    pass

class TimeRecordCreateAdmin(BaseModel):
    user_id: int
    record_type: RecordType
    record_datetime: datetime
    edit_justification: str = Field(..., max_length=300)

class TimeRecordUpdate(BaseModel):
    record_type: RecordType | None = None
    record_datetime: datetime | None = None
    edit_justification: str = Field(..., max_length=300)

class TimeRecordDeleteAdmin(BaseModel):
    edit_justification: str = Field(..., max_length=300)

class TimeRecordSimple(BaseModel):
    record_type: RecordType
    record_datetime: datetime
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