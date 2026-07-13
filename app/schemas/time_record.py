from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, AliasChoices
from typing import Optional

from app.domain.models.enums import RecordType


class SuccessResponse(BaseModel):
    status: str = "success"
    message: str

class TimeRecordBase(BaseModel):
    record_type: RecordType
    record_datetime: datetime
    ip_address: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None

class TimeRecordCreate(BaseModel):
    pass

class TimeRecordCreateAdmin(BaseModel):
    user_id: int
    record_type: RecordType
    record_datetime: datetime
    edit_justification: str = Field(..., max_length=70)

class TimeRecordUpdate(BaseModel):
    record_type: Optional[RecordType] = None
    record_datetime: Optional[datetime] = None
    edit_justification: str = Field(..., max_length=70)

class TimeRecordDeleteAdmin(BaseModel):
    edit_justification: str = Field(..., max_length=70)

class TimeRecordSimple(BaseModel):
    record_type: RecordType
    record_datetime: datetime
    model_config = ConfigDict(from_attributes=True)

class TimeRecordResponse(TimeRecordBase):
    id: int
    user_id: int
    created_at: datetime
    edited_by: Optional[str] = Field(None, validation_alias=AliasChoices('editor_name', 'edited_by'))
    edit_justification: Optional[str] = None
    original_record_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class TimeRecordTimelineResponse(TimeRecordResponse):
    is_ignored: bool
    model_config = ConfigDict(from_attributes=True)