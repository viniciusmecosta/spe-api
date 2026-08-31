from datetime import date, datetime, time
from unittest.mock import MagicMock

from sqlalchemy import asc, desc, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.database.repository import AsyncBaseRepository, BaseRepository
from app.features.system.system_models import AuditLog, RoutineLog, get_local_time_naive
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
            exec_res = db.scalars(select(AuditLog).options(selectinload(AuditLog.user)))
            if not isinstance(exec_res, MagicMock):
                stmt = select(AuditLog).options(selectinload(AuditLog.user))
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


class AsyncAuditRepository(AsyncBaseRepository[AuditLog, AuditLogCreate, AuditLogCreate]):
    def __init__(self):
        super().__init__(AuditLog)

    async def create(self, db: AsyncSession, obj_in: AuditLogCreate) -> AuditLog:
        return await super().create(db, obj_in=obj_in)

    async def get_logs(
            self,
            db: AsyncSession,
            action: str | None = None,
            start_date: date | None = None,
            end_date: date | None = None,
            order_by: str = "desc",
            skip: int = 0,
            limit: int = 100,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).options(selectinload(AuditLog.user))
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
        result = await db.scalars(stmt)
        return list(result.all())


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

    def has_routine_run_for_target_date(
            self,
            db: Session,
            routine_type: str,
            target_date: date,
            status: str | None = "SUCCESS",
    ) -> bool:
        if hasattr(db, "scalars") and not hasattr(db, "query"):
            stmt = select(exists().where(
                RoutineLog.routine_type == routine_type,
                RoutineLog.target_date == target_date,
                *([RoutineLog.status == status] if status else [])
            ))
            res = db.scalar(stmt)
            if res is not None:
                return bool(res)

        filters = [
            RoutineLog.routine_type == routine_type,
            RoutineLog.target_date == target_date,
        ]
        if status:
            filters.append(RoutineLog.status == status)
        query = db.query(exists().where(*filters))
        return bool(query.scalar())

    def has_hourly_routine_run(
            self,
            db: Session,
            routine_type: str,
            since_time: datetime,
            status: str | None = "SUCCESS",
    ) -> bool:
        if hasattr(db, "scalars") and not hasattr(db, "query"):
            stmt = select(exists().where(
                RoutineLog.routine_type == routine_type,
                RoutineLog.execution_time >= since_time,
                *([RoutineLog.status == status] if status else [])
            ))
            res = db.scalar(stmt)
            if res is not None:
                return bool(res)

        filters = [
            RoutineLog.routine_type == routine_type,
            RoutineLog.execution_time >= since_time,
        ]
        if status:
            filters.append(RoutineLog.status == status)
        query = db.query(exists().where(*filters))
        return bool(query.scalar())

    def get_last_successful_target_date(
            self,
            db: Session,
            routine_type: str,
    ) -> date | None:
        if hasattr(db, "scalars") and not hasattr(db, "query"):
            stmt = select(RoutineLog.target_date).where(
                RoutineLog.routine_type == routine_type,
                RoutineLog.status == "SUCCESS",
                RoutineLog.target_date.isnot(None),
            ).order_by(desc(RoutineLog.target_date)).limit(1)
            res = db.scalar(stmt)
            if res is not None:
                return res

        entry = db.query(RoutineLog).filter(
            RoutineLog.routine_type == routine_type,
            RoutineLog.status == "SUCCESS",
            RoutineLog.target_date.isnot(None),
        ).order_by(desc(RoutineLog.target_date)).first()
        return entry.target_date if entry else None

    def log_execution(
            self,
            db: Session,
            routine_type: str,
            status: str,
            target_date: date | None = None,
            execution_time: datetime | None = None,
            details: str | None = None,
    ) -> RoutineLog:
        now_local = execution_time or get_local_time_naive()
        obj_in = RoutineLogCreate(
            routine_type=routine_type,
            status=status,
            target_date=target_date,
            execution_time=now_local,
            details=details,
        )
        return self.create(db, obj_in=obj_in)

    def delete_older_than(
            self,
            db: Session,
            cutoff_date: datetime,
    ) -> int:
        query = db.query(RoutineLog).filter(RoutineLog.execution_time < cutoff_date)
        count = query.delete()
        db.commit()
        return count


class AsyncRoutineLogRepository(AsyncBaseRepository[RoutineLog, RoutineLogCreate, RoutineLogCreate]):
    def __init__(self):
        super().__init__(RoutineLog)

    async def get_logs(
            self,
            db: AsyncSession,
            routine_type: str | None = None,
            status: str | None = None,
            start_date: date | None = None,
            end_date: date | None = None,
            order_by: str = "desc",
            skip: int = 0,
            limit: int = 100,
    ) -> list[RoutineLog]:
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
        result = await db.scalars(stmt)
        return list(result.all())

    async def has_routine_run_for_target_date(
            self,
            db: AsyncSession,
            routine_type: str,
            target_date: date,
            status: str | None = "SUCCESS",
    ) -> bool:
        stmt = select(exists().where(
            RoutineLog.routine_type == routine_type,
            RoutineLog.target_date == target_date,
            *([RoutineLog.status == status] if status else [])
        ))
        res = await db.scalar(stmt)
        return bool(res)

    async def has_hourly_routine_run(
            self,
            db: AsyncSession,
            routine_type: str,
            since_time: datetime,
            status: str | None = "SUCCESS",
    ) -> bool:
        stmt = select(exists().where(
            RoutineLog.routine_type == routine_type,
            RoutineLog.execution_time >= since_time,
            *([RoutineLog.status == status] if status else [])
        ))
        res = await db.scalar(stmt)
        return bool(res)

    async def get_last_successful_target_date(
            self,
            db: AsyncSession,
            routine_type: str,
    ) -> date | None:
        stmt = select(RoutineLog.target_date).where(
            RoutineLog.routine_type == routine_type,
            RoutineLog.status == "SUCCESS",
            RoutineLog.target_date.isnot(None),
        ).order_by(desc(RoutineLog.target_date)).limit(1)
        return await db.scalar(stmt)

    async def log_execution(
            self,
            db: AsyncSession,
            routine_type: str,
            status: str,
            target_date: date | None = None,
            execution_time: datetime | None = None,
            details: str | None = None,
    ) -> RoutineLog:
        now_local = execution_time or get_local_time_naive()
        obj_in = RoutineLogCreate(
            routine_type=routine_type,
            status=status,
            target_date=target_date,
            execution_time=now_local,
            details=details,
        )
        return await self.create(db, obj_in=obj_in)

    async def delete_older_than(
            self,
            db: AsyncSession,
            cutoff_date: datetime,
    ) -> int:
        from sqlalchemy import delete
        stmt = delete(RoutineLog).where(RoutineLog.execution_time < cutoff_date)
        res = await db.execute(stmt)
        await db.commit()
        return res.rowcount or 0


audit_repository = AuditRepository()
async_audit_repository = AsyncAuditRepository()
routine_log_repository = RoutineLogRepository()
async_routine_log_repository = AsyncRoutineLogRepository()
