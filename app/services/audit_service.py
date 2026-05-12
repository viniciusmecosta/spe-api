from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, Any

from app.repositories.audit_repository import audit_repository
from app.schemas.audit import AuditLogCreate


class AuditService:
    def log(self, db: Session, action: str, entity: str,
            actor_id: Optional[int] = None, target_user_id: Optional[int] = None,
            entity_id: Optional[int] = None, old_data: Optional[Any] = None,
            new_data: Optional[Any] = None, user_id: Optional[int] = None,
            details: Optional[str] = None, actor_name: Optional[str] = None,
            target_user_name: Optional[str] = None, justification: Optional[str] = None,
            reason: Optional[str] = None, record_time: Optional[datetime] = None,
            record_type: Optional[str] = None):
        final_actor_id = actor_id if actor_id is not None else user_id
        final_user_id = user_id if user_id is not None else actor_id

        obj_in = AuditLogCreate(
            actor_id=final_actor_id,
            target_user_id=target_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_data=old_data,
            new_data=new_data,
            user_id=final_user_id,
            details=details,
            actor_name=actor_name,
            target_user_name=target_user_name,
            justification=justification,
            reason=reason,
            record_time=record_time,
            record_type=record_type
        )
        return audit_repository.create(db, obj_in)


audit_service = AuditService()
