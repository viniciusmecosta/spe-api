from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.repository import AsyncBaseRepository, BaseRepository
from app.features.payroll.payroll_models import PayrollClosure


class PayrollRepository(BaseRepository[PayrollClosure, Any, Any]):
    def __init__(self):
        super().__init__(PayrollClosure)

    def create(
            self,
            db: Session,
            *,
            obj_in: Any | None = None,
            month: int | None = None,
            year: int | None = None,
            user_id: int | None = None,
    ) -> PayrollClosure:
        if obj_in is not None:
            if isinstance(obj_in, PayrollClosure):
                db_obj = obj_in
            elif isinstance(obj_in, dict):
                db_obj = PayrollClosure(**obj_in)
            else:
                db_obj = PayrollClosure(
                    month=getattr(obj_in, "month", month),
                    year=getattr(obj_in, "year", year),
                    is_closed=True,
                    closed_by_user_id=getattr(obj_in, "user_id", user_id),
                )
        else:
            db_obj = PayrollClosure(month=month, year=year, is_closed=True, closed_by_user_id=user_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_month(self, db: Session, month: int, year: int) -> PayrollClosure | None:
        stmt = select(PayrollClosure).where(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
            PayrollClosure.deleted_at.is_(None),
        )
        return db.scalars(stmt).first()

    def get_all(self, db: Session, year: int | None = None) -> list[PayrollClosure]:
        stmt = select(PayrollClosure).where(PayrollClosure.deleted_at.is_(None))
        if year:
            stmt = stmt.where(PayrollClosure.year == year)
        stmt = stmt.order_by(
            PayrollClosure.year.desc(),
            PayrollClosure.month.desc(),
        )
        return list(db.scalars(stmt).all())

    def get_history(self, db: Session, month: int, year: int) -> list[PayrollClosure]:
        stmt = select(PayrollClosure).where(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
        ).order_by(PayrollClosure.id.asc())
        return list(db.scalars(stmt).all())

    def delete(self, db: Session, month: int, year: int, user_id: int, observation: str):
        stmt = select(PayrollClosure).where(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
            PayrollClosure.deleted_at.is_(None),
        )
        record = db.scalars(stmt).first()
        if record:
            record.deleted_at = datetime.now()
            record.deleted_by = user_id
            record.reopen_observation = observation
            db.commit()


class AsyncPayrollRepository(AsyncBaseRepository[PayrollClosure, Any, Any]):
    def __init__(self):
        super().__init__(PayrollClosure)

    async def create(
            self,
            db: AsyncSession,
            *,
            obj_in: Any | None = None,
            month: int | None = None,
            year: int | None = None,
            user_id: int | None = None,
    ) -> PayrollClosure:
        if obj_in is not None:
            if isinstance(obj_in, PayrollClosure):
                db_obj = obj_in
            elif isinstance(obj_in, dict):
                db_obj = PayrollClosure(**obj_in)
            else:
                db_obj = PayrollClosure(
                    month=getattr(obj_in, "month", month),
                    year=getattr(obj_in, "year", year),
                    is_closed=True,
                    closed_by_user_id=getattr(obj_in, "user_id", user_id),
                )
        else:
            db_obj = PayrollClosure(month=month, year=year, is_closed=True, closed_by_user_id=user_id)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_by_month(self, db: AsyncSession, month: int, year: int) -> PayrollClosure | None:
        stmt = select(PayrollClosure).where(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
            PayrollClosure.deleted_at.is_(None),
        )
        result = await db.scalars(stmt)
        return result.first()

    async def get_all(self, db: AsyncSession, year: int | None = None) -> list[PayrollClosure]:
        stmt = select(PayrollClosure).where(PayrollClosure.deleted_at.is_(None))
        if year:
            stmt = stmt.where(PayrollClosure.year == year)
        stmt = stmt.order_by(
            PayrollClosure.year.desc(),
            PayrollClosure.month.desc(),
        )
        result = await db.scalars(stmt)
        return list(result.all())

    async def get_history(self, db: AsyncSession, month: int, year: int) -> list[PayrollClosure]:
        stmt = select(PayrollClosure).where(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
        ).order_by(PayrollClosure.id.asc())
        result = await db.scalars(stmt)
        return list(result.all())

    async def delete(self, db: AsyncSession, month: int, year: int, user_id: int, observation: str):
        stmt = select(PayrollClosure).where(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
            PayrollClosure.deleted_at.is_(None),
        )
        result = await db.scalars(stmt)
        record = result.first()
        if record:
            record.deleted_at = datetime.now()
            record.deleted_by = user_id
            record.reopen_observation = observation
            await db.commit()


payroll_repository = PayrollRepository()
async_payroll_repository = AsyncPayrollRepository()
