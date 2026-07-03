from datetime import datetime, date
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
        
    def get_logs(self, db: Session, action: Optional[str] = None, 
                 start_date: Optional[date] = None, end_date: Optional[date] = None,
                 order_by: str = "desc", skip: int = 0, limit: int = 100):
        return audit_repository.get_logs(
            db, action=action, start_date=start_date, end_date=end_date,
            order_by=order_by, skip=skip, limit=limit
        )


audit_service = AuditService()
