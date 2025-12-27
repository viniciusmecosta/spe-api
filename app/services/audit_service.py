from sqlalchemy.orm import Session
from app.repositories.audit_repository import audit_repository
from app.schemas.audit import AuditLogCreate

class AuditService:
    def log(self, db: Session, user_id: int, action: str, entity: str, entity_id: int = None, details: str = None):
        audit_in = AuditLogCreate(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details
        )
        audit_repository.create(db, audit_in)

audit_service = AuditService()