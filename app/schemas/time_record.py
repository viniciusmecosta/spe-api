from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from app.domain.models.enums import RecordType


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


class TimeRecordUpdate(BaseModel):
    record_type: Optional[RecordType] = None
    record_datetime: Optional[datetime] = None


class TimeRecordResponse(TimeRecordBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
