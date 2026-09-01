from datetime import date
from typing import Any

from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.database.repository import AsyncBaseRepository, BaseRepository
from app.features.adjustments.adjustment_models import (
    AdjustmentAttachment,
    AdjustmentRequest,
    get_local_time,
)
from app.features.adjustments.adjustment_schemas import AdjustmentRequestCreate
from app.shared.enums import AdjustmentStatus, AdjustmentType


class AdjustmentRepository(BaseRepository[AdjustmentRequest, AdjustmentRequestCreate, Any]):
    def __init__(self):
        super().__init__(AdjustmentRequest)

    def create(
            self,
            db: Session,
            *,
            obj_in: AdjustmentRequestCreate,
            user_id: int | None = None,
    ) -> AdjustmentRequest:
        target_user_id = user_id if user_id is not None else getattr(obj_in, "user_id", None)
        db_obj = AdjustmentRequest(
            user_id=target_user_id,
            adjustment_type=obj_in.adjustment_type,
            record_type=obj_in.record_type,
            target_date=obj_in.target_date,
            time=obj_in.time,
            amount_hours=obj_in.amount_hours,
            reason_text=obj_in.reason_text,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: Any) -> AdjustmentRequest | None:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(
                AdjustmentRequest.id == id,
                AdjustmentRequest.deleted_at.is_(None),
            )
        )
        return db.scalars(stmt).first()

    def get_all_by_user(
        self,
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        month: int | None = None,
        year: int | None = None,
        status: str | None = None,
        order_by: str = "created_at",
        order_direction: str = "desc",
    ) -> list[AdjustmentRequest]:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.deleted_at.is_(None),
                ~and_(
                    AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
                    AdjustmentRequest.status == AdjustmentStatus.PENDING
                )
            )
        )

        if month and year:
            stmt = stmt.where(
                func.extract("month", AdjustmentRequest.target_date) == month,
                func.extract("year", AdjustmentRequest.target_date) == year,
            )
        elif year:
            stmt = stmt.where(func.extract("year", AdjustmentRequest.target_date) == year)

        if status:
            if status.upper() == "NOT_PENDING":
                stmt = stmt.where(AdjustmentRequest.status != AdjustmentStatus.PENDING)
            else:
                stmt = stmt.where(AdjustmentRequest.status == AdjustmentStatus(status.upper()))

        order_column = (
            AdjustmentRequest.target_date
            if order_by == "target_date"
            else func.coalesce(AdjustmentRequest.reviewed_at, AdjustmentRequest.created_at)
        )
        stmt = stmt.order_by(desc(order_column) if order_direction == "desc" else order_column)
        stmt = stmt.offset(skip).limit(limit)

        return list(db.scalars(stmt).all())

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        month: int | None = None,
        year: int | None = None,
        status: str | None = None,
        order_by: str = "created_at",
        order_direction: str = "desc",
    ) -> list[AdjustmentRequest]:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(AdjustmentRequest.deleted_at.is_(None))
        )

        if month and year:
            stmt = stmt.where(
                func.extract("month", AdjustmentRequest.target_date) == month,
                func.extract("year", AdjustmentRequest.target_date) == year,
            )
        elif year:
            stmt = stmt.where(func.extract("year", AdjustmentRequest.target_date) == year)

        if status:
            if status.upper() == "NOT_PENDING":
                stmt = stmt.where(AdjustmentRequest.status != AdjustmentStatus.PENDING)
            else:
                stmt = stmt.where(AdjustmentRequest.status == AdjustmentStatus(status.upper()))

        order_column = (
            AdjustmentRequest.target_date
            if order_by == "target_date"
            else func.coalesce(AdjustmentRequest.reviewed_at, AdjustmentRequest.created_at)
        )
        stmt = stmt.order_by(desc(order_column) if order_direction == "desc" else order_column)
        stmt = stmt.offset(skip).limit(limit)

        return list(db.scalars(stmt).all())

    def count_pending(self, db: Session, from_date: date | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(AdjustmentRequest)
            .where(
                AdjustmentRequest.status == AdjustmentStatus.PENDING,
                AdjustmentRequest.deleted_at.is_(None),
            )
        )
        if from_date:
            stmt = stmt.where(AdjustmentRequest.target_date >= from_date)
        return db.scalar(stmt) or 0

    def get_waivers_by_user_and_date(
        self, db: Session, user_id: int, target_date: date
    ) -> list[AdjustmentRequest]:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(
                and_(
                    AdjustmentRequest.user_id == user_id,
                    AdjustmentRequest.target_date == target_date,
                    AdjustmentRequest.adjustment_type == AdjustmentType.WAIVER,
                    AdjustmentRequest.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.APPROVED]),
                    AdjustmentRequest.deleted_at.is_(None),
                )
            )
        )
        return list(db.scalars(stmt).all())

    def update_status(
        self,
        db: Session,
        db_obj: AdjustmentRequest,
        status: AdjustmentStatus,
        manager_id: int,
        comment: str | None = None,
    ) -> AdjustmentRequest:
        db_obj.status = status
        db_obj.manager_id = manager_id
        db_obj.manager_comment = comment
        db_obj.reviewed_at = get_local_time()
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_attachment(
        self, db: Session, request_id: int, file_path: str, file_type: str
    ) -> AdjustmentAttachment:
        db_attachment = AdjustmentAttachment(
            adjustment_request_id=request_id,
            file_path=file_path,
            file_type=file_type,
        )
        db.add(db_attachment)
        db.commit()
        db.refresh(db_attachment)
        return db_attachment

    def soft_delete(self, db: Session, id: int, user_id: int):
        db_obj = self.get(db, id)
        if db_obj:
            db_obj.deleted_at = get_local_time()
            db_obj.deleted_by = user_id
            db.add(db_obj)
            db.commit()

    def delete(self, db: Session, id: int):
        db.execute(delete(AdjustmentAttachment).where(AdjustmentAttachment.adjustment_request_id == id))
        db.execute(delete(AdjustmentRequest).where(AdjustmentRequest.id == id))
        db.commit()


class AsyncAdjustmentRepository(AsyncBaseRepository[AdjustmentRequest, AdjustmentRequestCreate, Any]):
    def __init__(self):
        super().__init__(AdjustmentRequest)

    async def create(
            self,
            db: AsyncSession,
            *,
            obj_in: AdjustmentRequestCreate,
            user_id: int | None = None,
    ) -> AdjustmentRequest:
        target_user_id = user_id if user_id is not None else getattr(obj_in, "user_id", None)
        db_obj = AdjustmentRequest(
            user_id=target_user_id,
            adjustment_type=obj_in.adjustment_type,
            record_type=obj_in.record_type,
            target_date=obj_in.target_date,
            time=obj_in.time,
            amount_hours=obj_in.amount_hours,
            reason_text=obj_in.reason_text,
        )
        db.add(db_obj)
        await db.commit()
        refreshed = await self.get(db, db_obj.id)
        return refreshed if refreshed else db_obj

    async def get(self, db: AsyncSession, id: Any) -> AdjustmentRequest | None:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(
                AdjustmentRequest.id == id,
                AdjustmentRequest.deleted_at.is_(None),
            )
        )
        result = await db.scalars(stmt)
        return result.first()

    async def get_all_by_user(
            self,
            db: AsyncSession,
            user_id: int,
            skip: int = 0,
            limit: int = 100,
            month: int | None = None,
            year: int | None = None,
            status: str | None = None,
            order_by: str = "created_at",
            order_direction: str = "desc",
    ) -> list[AdjustmentRequest]:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.deleted_at.is_(None),
                ~and_(
                    AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
                    AdjustmentRequest.status == AdjustmentStatus.PENDING
                )
            )
        )

        if month and year:
            stmt = stmt.where(
                func.extract("month", AdjustmentRequest.target_date) == month,
                func.extract("year", AdjustmentRequest.target_date) == year,
            )
        elif year:
            stmt = stmt.where(func.extract("year", AdjustmentRequest.target_date) == year)

        if status:
            if status.upper() == "NOT_PENDING":
                stmt = stmt.where(AdjustmentRequest.status != AdjustmentStatus.PENDING)
            else:
                stmt = stmt.where(AdjustmentRequest.status == AdjustmentStatus(status.upper()))

        order_column = (
            AdjustmentRequest.target_date
            if order_by == "target_date"
            else func.coalesce(AdjustmentRequest.reviewed_at, AdjustmentRequest.created_at)
        )
        stmt = stmt.order_by(desc(order_column) if order_direction == "desc" else order_column)
        stmt = stmt.offset(skip).limit(limit)

        result = await db.scalars(stmt)
        return list(result.all())

    async def get_all(
            self,
            db: AsyncSession,
            skip: int = 0,
            limit: int = 100,
            month: int | None = None,
            year: int | None = None,
            status: str | None = None,
            order_by: str = "created_at",
            order_direction: str = "desc",
    ) -> list[AdjustmentRequest]:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(AdjustmentRequest.deleted_at.is_(None))
        )

        if month and year:
            stmt = stmt.where(
                func.extract("month", AdjustmentRequest.target_date) == month,
                func.extract("year", AdjustmentRequest.target_date) == year,
            )
        elif year:
            stmt = stmt.where(func.extract("year", AdjustmentRequest.target_date) == year)

        if status:
            if status.upper() == "NOT_PENDING":
                stmt = stmt.where(AdjustmentRequest.status != AdjustmentStatus.PENDING)
            else:
                stmt = stmt.where(AdjustmentRequest.status == AdjustmentStatus(status.upper()))

        order_column = (
            AdjustmentRequest.target_date
            if order_by == "target_date"
            else func.coalesce(AdjustmentRequest.reviewed_at, AdjustmentRequest.created_at)
        )
        stmt = stmt.order_by(desc(order_column) if order_direction == "desc" else order_column)
        stmt = stmt.offset(skip).limit(limit)

        result = await db.scalars(stmt)
        return list(result.all())

    async def count_pending(self, db: AsyncSession, from_date: date | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(AdjustmentRequest)
            .where(
                AdjustmentRequest.status == AdjustmentStatus.PENDING,
                AdjustmentRequest.deleted_at.is_(None),
            )
        )
        if from_date:
            stmt = stmt.where(AdjustmentRequest.target_date >= from_date)
        result = await db.scalar(stmt)
        return result or 0

    async def get_waivers_by_user_and_date(
            self, db: AsyncSession, user_id: int, target_date: date
    ) -> list[AdjustmentRequest]:
        stmt = (
            select(AdjustmentRequest)
            .options(
                selectinload(AdjustmentRequest.user),
                selectinload(AdjustmentRequest.manager),
                selectinload(AdjustmentRequest.attachments),
            )
            .where(
                and_(
                    AdjustmentRequest.user_id == user_id,
                    AdjustmentRequest.target_date == target_date,
                    AdjustmentRequest.adjustment_type == AdjustmentType.WAIVER,
                    AdjustmentRequest.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.APPROVED]),
                    AdjustmentRequest.deleted_at.is_(None),
                )
            )
        )
        result = await db.scalars(stmt)
        return list(result.all())

    async def update_status(
            self,
            db: AsyncSession,
            db_obj: AdjustmentRequest,
            status: AdjustmentStatus,
            manager_id: int,
            comment: str | None = None,
    ) -> AdjustmentRequest:
        db_obj.status = status
        db_obj.manager_id = manager_id
        db_obj.manager_comment = comment
        db_obj.reviewed_at = get_local_time()
        db.add(db_obj)
        await db.commit()
        refreshed = await self.get(db, db_obj.id)
        return refreshed if refreshed else db_obj

    async def create_attachment(
            self, db: AsyncSession, request_id: int, file_path: str, file_type: str
    ) -> AdjustmentAttachment:
        db_attachment = AdjustmentAttachment(
            adjustment_request_id=request_id,
            file_path=file_path,
            file_type=file_type,
        )
        db.add(db_attachment)
        await db.commit()
        await db.refresh(db_attachment)
        return db_attachment

    async def soft_delete(self, db: AsyncSession, id: int, user_id: int):
        db_obj = await self.get(db, id)
        if db_obj:
            db_obj.deleted_at = get_local_time()
            db_obj.deleted_by = user_id
            db.add(db_obj)
            await db.commit()

    async def delete(self, db: AsyncSession, id: int):
        await db.execute(delete(AdjustmentAttachment).where(AdjustmentAttachment.adjustment_request_id == id))
        await db.execute(delete(AdjustmentRequest).where(AdjustmentRequest.id == id))
        await db.commit()


adjustment_repository = AdjustmentRepository()
async_adjustment_repository = AsyncAdjustmentRepository()
