from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.domain.models.enums import RecordType


class TimeRecordBase(BaseModel):
    record_type: RecordType
    record_datetime: datetime
    ip_address: Optional[str] = None


class TimeRecordCreate(BaseModel):
    pass


class TimeRecordResponse(TimeRecordBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
