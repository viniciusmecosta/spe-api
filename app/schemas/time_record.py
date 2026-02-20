from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from app.domain.models.enums import RecordType, EditJustification

class TimeRecordBase(BaseModel):
    record_type: RecordType
    record_datetime: datetime
    ip_address: Optional[str] = None

class TimeRecordCreate(BaseModel):
    pass

class TimeRecordCreateAdmin(BaseModel):
    user_id: int
    record_type: RecordType
    record_datetime: datetime
    edit_justification: EditJustification
    edit_reason: Optional[str] = None

class TimeRecordUpdate(BaseModel):
    record_type: Optional[RecordType] = None
    record_datetime: Optional[datetime] = None
    edit_justification: Optional[EditJustification] = None
    edit_reason: Optional[str] = None

class TimeRecordDeleteAdmin(BaseModel):
    edit_justification: EditJustification
    edit_reason: Optional[str] = None

class TimeRecordResponse(TimeRecordBase):
    id: int
    user_id: int
    created_at: datetime
    is_manual: bool
    edited_by: Optional[int] = None
    edit_justification: Optional[EditJustification] = None
    edit_reason: Optional[str] = None

    class Config:
        from_attributes = True