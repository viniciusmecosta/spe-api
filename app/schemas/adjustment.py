from typing import Optional
from datetime import date, time, datetime
from pydantic import BaseModel
from app.domain.models.enums import AdjustmentType, AdjustmentStatus

class AdjustmentRequestBase(BaseModel):
    adjustment_type: AdjustmentType
    target_date: date
    reason_text: Optional[str] = None
    entry_time: Optional[time] = None
    exit_time: Optional[time] = None

class AdjustmentRequestCreate(AdjustmentRequestBase):
    pass

class AdjustmentRequestResponse(AdjustmentRequestBase):
    id: int
    user_id: int
    status: AdjustmentStatus
    manager_id: Optional[int] = None
    manager_comment: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True