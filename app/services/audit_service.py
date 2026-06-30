from datetime import datetime
from typing import Optional, Any

from sqlalchemy.orm import Session

from app.repositories.audit_repository import audit_repository
from app.schemas.audit import AuditLogCreate


class AuditService:
    def log(self, db: Session, *, action: str, entity: str, entity_id: int,
            user_id: Optional[int] = None,
            old_data: Optional[dict] = None, new_data: Optional[dict] = None):
        obj_in = AuditLogCreate(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_data=old_data,
            new_data=new_data
        )
        return audit_repository.create(db, obj_in)


audit_service = AuditService()
