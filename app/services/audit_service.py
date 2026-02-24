from sqlalchemy.orm import Session
from typing import Optional, Any

from app.repositories.audit_repository import audit_repository
from app.schemas.audit import AuditLogCreate


class AuditService:
    def log(self, db: Session, action: str, entity: str, actor_id: Optional[int] = None,
            target_user_id: Optional[int] = None, entity_id: Optional[int] = None,
            old_data: Optional[Any] = None, new_data: Optional[Any] = None):
        obj_in = AuditLogCreate(
            actor_id=actor_id,
            target_user_id=target_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_data=old_data,
            new_data=new_data
        )
        return audit_repository.create(db, obj_in)


audit_service = AuditService()
