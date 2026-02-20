from sqlalchemy import desc, asc
from sqlalchemy.orm import Session
from typing import Optional

from app.domain.models.audit import AuditLog
from app.schemas.audit import AuditLogCreate

class AuditRepository:
    def create(self, db: Session, obj_in: AuditLogCreate) -> AuditLog:
        db_obj = AuditLog(
            user_id=obj_in.user_id,
            action=obj_in.action,
            entity=obj_in.entity,
            entity_id=obj_in.entity_id,
            details=obj_in.details,
            actor_name=obj_in.actor_name,
            target_user_id=obj_in.target_user_id,
            target_user_name=obj_in.target_user_name,
            justification=obj_in.justification,
            reason=obj_in.reason,
            record_time=obj_in.record_time,
            record_type=obj_in.record_type
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_logs(self, db: Session, action: Optional[str] = None, order_by: str = "desc", skip: int = 0, limit: int = 100):
        query = db.query(AuditLog)
        if action:
            query = query.filter(AuditLog.action == action)
        if order_by.lower() == "asc":
            query = query.order_by(asc(AuditLog.timestamp))
        else:
            query = query.order_by(desc(AuditLog.timestamp))
        return query.offset(skip).limit(limit).all()

    def get_manual_changes(self, db: Session, order_by: str = "desc", skip: int = 0, limit: int = 100):
        query = db.query(AuditLog).filter(AuditLog.action.in_(["CREATE_RECORD_ADMIN", "UPDATE_RECORD_ADMIN", "DELETE_RECORD_ADMIN", "TOGGLE_RECORD"]))
        if order_by.lower() == "asc":
            query = query.order_by(asc(AuditLog.timestamp))
        else:
            query = query.order_by(desc(AuditLog.timestamp))
        return query.offset(skip).limit(limit).all()

audit_repository = AuditRepository()