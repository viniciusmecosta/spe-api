from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class AuditLogBase(BaseModel):
    user_id: int
    action: str
    entity: str
    entity_id: Optional[int] = None
    details: Optional[str] = None
    actor_name: Optional[str] = None
    target_user_id: Optional[int] = None
    target_user_name: Optional[str] = None
    justification: Optional[str] = None
    reason: Optional[str] = None
    record_time: Optional[datetime] = None
    record_type: Optional[str] = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogResponse(AuditLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True
