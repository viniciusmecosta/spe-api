from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from app.repositories.audit_repository import audit_repository
from app.schemas.audit import AuditLogCreate

class AuditService:
    def log(self, db: Session, user_id: int, action: str, entity: str, entity_id: Optional[int] = None, details: Optional[str] = None, actor_name: Optional[str] = None, target_user_id: Optional[int] = None, target_user_name: Optional[str] = None, justification: Optional[str] = None, reason: Optional[str] = None, record_time: Optional[datetime] = None, record_type: Optional[str] = None):
        obj_in = AuditLogCreate(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
            actor_name=actor_name,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            justification=justification,
            reason=reason,
            record_time=record_time,
            record_type=record_type
        )
        return audit_repository.create(db, obj_in)

audit_service = AuditService()