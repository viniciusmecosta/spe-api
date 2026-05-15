from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Any


class UserSnapshot(BaseModel):
    id: int
    name: str
    username: str
    role: str

    class Config:
        from_attributes = True


class AuditLogBase(BaseModel):
    actor_id: Optional[int] = None
    target_user_id: Optional[int] = None
    action: str
    entity: str
    entity_id: Optional[int] = None
    old_data: Optional[Any] = None
    new_data: Optional[Any] = None

    user_id: Optional[int] = None
    details: Optional[str] = None
    actor_name: Optional[str] = None
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
    actor: Optional[UserSnapshot] = None
    target_user: Optional[UserSnapshot] = None

    class Config:
        from_attributes = True
