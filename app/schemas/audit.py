from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel


class UserSnapshot(BaseModel):
    id: int
    name: str
    username: str
    role: str

    class Config:
        from_attributes = True


class AuditLogBase(BaseModel):
    user_id: Optional[int] = None
    action: str
    entity: str
    entity_id: Optional[int] = None
    old_data: Optional[Any] = None
    new_data: Optional[Any] = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogResponse(AuditLogBase):
    id: int
    timestamp: datetime
    user: Optional[UserSnapshot] = None

    class Config:
        from_attributes = True
