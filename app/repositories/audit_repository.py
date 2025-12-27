from sqlalchemy.orm import Session
from app.domain.models.audit import AuditLog
from app.schemas.audit import AuditLogCreate

class AuditRepository:
    def create(self, db: Session, obj_in: AuditLogCreate) -> AuditLog:
        db_obj = AuditLog(
            user_id=obj_in.user_id,
            action=obj_in.action,
            entity=obj_in.entity,
            entity_id=obj_in.entity_id,
            details=obj_in.details
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

audit_repository = AuditRepository()