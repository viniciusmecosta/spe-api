from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class UserSnapshot(BaseModel):
    id: int
    name: str
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class AuditLogBase(BaseModel):
    user_id: int | None = None
    action: str
    entity: str
    entity_id: int | None = None
    old_data: Any | None = None
    new_data: Any | None = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogResponse(AuditLogBase):
    id: int
    timestamp: datetime
    user: UserSnapshot | None = None

    model_config = ConfigDict(from_attributes=True)
