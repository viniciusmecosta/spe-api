from datetime import date, datetime, time

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.features.system.system_models import AuditLog, RoutineLog
from app.features.system.system_schemas import AuditLogCreate


class AuditRepository:
    def create(self, db: Session, obj_in: AuditLogCreate) -> AuditLog:
        db_obj = AuditLog(
            user_id=obj_in.user_id,
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

    def get_logs(self, db: Session, action: str | None = None,
                 start_date: date | None = None, end_date: date | None = None,
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

    def get_manual_changes(self, db: Session, start_date: date | None = None, end_date: date | None = None,
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


class RoutineLogRepository:
    def get_logs(
            self,
            db: Session,
            routine_type: str | None = None,
            status: str | None = None,
            start_date: date | None = None,
            end_date: date | None = None,
            order_by: str = "desc",
            skip: int = 0,
            limit: int = 100
    ) -> list[RoutineLog]:
        query = db.query(RoutineLog)

        if routine_type:
            query = query.filter(RoutineLog.routine_type == routine_type)

        if status:
            query = query.filter(RoutineLog.status == status)

        if start_date:
            start_dt = datetime.combine(start_date, time.min)
            query = query.filter(RoutineLog.execution_time >= start_dt)

        if end_date:
            end_dt = datetime.combine(end_date, time.max)
            query = query.filter(RoutineLog.execution_time <= end_dt)

        if order_by == "asc":
            query = query.order_by(asc(RoutineLog.execution_time))
        else:
            query = query.order_by(desc(RoutineLog.execution_time))

        return query.offset(skip).limit(limit).all()


audit_repository = AuditRepository()
routine_log_repository = RoutineLogRepository()
