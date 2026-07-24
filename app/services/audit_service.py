from datetime import date

from sqlalchemy.orm import Session

from app.repositories.audit_repository import audit_repository
from app.schemas.audit import AuditLogCreate


class AuditService:
    def log(self, db: Session, *, action: str, entity: str, entity_id: int,
            user_id: int | None = None,
            old_data: dict | None = None, new_data: dict | None = None):
        obj_in = AuditLogCreate(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_data=old_data,
            new_data=new_data
        )
        return audit_repository.create(db, obj_in)

    def compute_diffs(self, old_data: dict, new_data: dict) -> tuple[dict, dict]:
        actual_old = {}
        actual_new = {}
        
        all_keys = set(old_data.keys()).union(new_data.keys())
        for key in all_keys:
            old_val = old_data.get(key)
            new_val = new_data.get(key)
            if old_val != new_val:
                if key in old_data:
                    actual_old[key] = old_val
                if key in new_data:
                    actual_new[key] = new_val
                    
        return actual_old, actual_new

    def get_logs(self, db: Session, action: str | None = None,
                 start_date: date | None = None, end_date: date | None = None,
                 order_by: str = "desc", skip: int = 0, limit: int = 100):
        return audit_repository.get_logs(
            db, action=action, start_date=start_date, end_date=end_date,
            order_by=order_by, skip=skip, limit=limit
        )


audit_service = AuditService()
