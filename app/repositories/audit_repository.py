from datetime import date, datetime, time
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session
from typing import Optional

from app.domain.models.audit import AuditLog
from app.schemas.audit import AuditLogCreate


class AuditRepository:
    def create(self, db: Session, obj_in: AuditLogCreate) -> AuditLog:
        db_obj = AuditLog(
            actor_id=obj_in.actor_id,
            target_user_id=obj_in.target_user_id,
            action=obj_in.action,
            entity=obj_in.entity,
            entity_id=obj_in.entity_id,
            old_data=obj_in.old_data,
            new_data=obj_in.new_data
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_logs(self, db: Session, action: Optional[str] = None,
                 start_date: Optional[date] = None, end_date: Optional[date] = None,
                 order_by: str = "desc", skip: int = 0, limit: int = 100):
        query = db.query(AuditLog)
        if action:
            query = query.filter(AuditLog.action == action)
        if start_date:
            dt_start = datetime.combine(start_date, time.min)
            query = query.filter(AuditLog.timestamp >= dt_start)
        if end_date:
            dt_end = datetime.combine(end_date, time.max)
            query = query.filter(AuditLog.timestamp <= dt_end)

        if order_by.lower() == "asc":
            query = query.order_by(asc(AuditLog.timestamp))
        else:
            query = query.order_by(desc(AuditLog.timestamp))
        return query.offset(skip).limit(limit).all()

    def get_manual_changes(self, db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None,
                           order_by: str = "desc", skip: int = 0, limit: int = 100):
        query = db.query(AuditLog)

        if start_date:
            dt_start = datetime.combine(start_date, time.min)
            query = query.filter(AuditLog.timestamp >= dt_start)
        if end_date:
            dt_end = datetime.combine(end_date, time.max)
            query = query.filter(AuditLog.timestamp <= dt_end)

        if order_by.lower() == "asc":
            query = query.order_by(asc(AuditLog.timestamp))
        else:
            query = query.order_by(desc(AuditLog.timestamp))
        return query.offset(skip).limit(limit).all()


audit_repository = AuditRepository()
