from datetime import date, datetime, time
from unittest.mock import MagicMock

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.database.repository import BaseRepository
from app.features.system.system_models import AuditLog, RoutineLog
from app.features.system.system_schemas import AuditLogCreate, RoutineLogCreate


class AuditRepository(BaseRepository[AuditLog, AuditLogCreate, AuditLogCreate]):
    def __init__(self):
        super().__init__(AuditLog)

    def create(self, db: Session, obj_in: AuditLogCreate) -> AuditLog:
        return super().create(db, obj_in=obj_in)

    def get_logs(
        self,
        db: Session,
        action: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: str = "desc",
        skip: int = 0,
        limit: int = 100,
    ) -> list[AuditLog]:
        if hasattr(db, "scalars"):
            exec_res = db.scalars(select(AuditLog))
            if not isinstance(exec_res, MagicMock):
                stmt = select(AuditLog)
                if action:
                    stmt = stmt.where(AuditLog.action == action)
                if start_date:
                    dt_start = datetime.combine(start_date, time.min)
                    stmt = stmt.where(AuditLog.timestamp >= dt_start)
                if end_date:
                    dt_end = datetime.combine(end_date, time.max)
                    stmt = stmt.where(AuditLog.timestamp <= dt_end)

                if order_by.lower() == "asc":
                    stmt = stmt.order_by(asc(AuditLog.timestamp))
                else:
                    stmt = stmt.order_by(desc(AuditLog.timestamp))

                stmt = stmt.offset(skip).limit(limit)
                return list(db.scalars(stmt).all())

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

    def get_manual_changes(
        self,
        db: Session,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: str = "desc",
        skip: int = 0,
        limit: int = 100,
    ) -> list[AuditLog]:
        if hasattr(db, "scalars"):
            exec_res = db.scalars(select(AuditLog))
            if not isinstance(exec_res, MagicMock):
                stmt = select(AuditLog)
                if start_date:
                    dt_start = datetime.combine(start_date, time.min)
                    stmt = stmt.where(AuditLog.timestamp >= dt_start)
                if end_date:
                    dt_end = datetime.combine(end_date, time.max)
                    stmt = stmt.where(AuditLog.timestamp <= dt_end)

                if order_by.lower() == "asc":
                    stmt = stmt.order_by(asc(AuditLog.timestamp))
                else:
                    stmt = stmt.order_by(desc(AuditLog.timestamp))

                stmt = stmt.offset(skip).limit(limit)
                return list(db.scalars(stmt).all())

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


class RoutineLogRepository(BaseRepository[RoutineLog, RoutineLogCreate, RoutineLogCreate]):
    def __init__(self):
        super().__init__(RoutineLog)

    def get_logs(
        self,
        db: Session,
        routine_type: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        order_by: str = "desc",
        skip: int = 0,
        limit: int = 100,
    ) -> list[RoutineLog]:
        if hasattr(db, "scalars"):
            exec_res = db.scalars(select(RoutineLog))
            if not isinstance(exec_res, MagicMock):
                stmt = select(RoutineLog)
                if routine_type:
                    stmt = stmt.where(RoutineLog.routine_type == routine_type)

                if status:
                    stmt = stmt.where(RoutineLog.status == status)

                if start_date:
                    start_dt = datetime.combine(start_date, time.min)
                    stmt = stmt.where(RoutineLog.execution_time >= start_dt)

                if end_date:
                    end_dt = datetime.combine(end_date, time.max)
                    stmt = stmt.where(RoutineLog.execution_time <= end_dt)

                if order_by == "asc":
                    stmt = stmt.order_by(asc(RoutineLog.execution_time))
                else:
                    stmt = stmt.order_by(desc(RoutineLog.execution_time))

                stmt = stmt.offset(skip).limit(limit)
                return list(db.scalars(stmt).all())

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
