from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.unit_of_work import persist_changes, persist_sync_changes


class BaseRepository[
    ModelType: Base,
    CreateSchemaType: BaseModel | dict[str, Any],
    UpdateSchemaType: BaseModel | dict[str, Any],
]:
    def __init__(self, model: type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> ModelType | None:
        return db.get(self.model, id)

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        stmt = select(self.model).offset(skip).limit(limit)
        return db.scalars(stmt).all()

    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        if isinstance(obj_in, dict):
            create_data = obj_in
        elif hasattr(obj_in, "model_dump"):
            create_data = obj_in.model_dump(exclude_unset=True)
        else:
            create_data = vars(obj_in)
        db_obj = self.model(**create_data)
        db.add(db_obj)
        persist_sync_changes(db)
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any]
    ) -> ModelType:
        if isinstance(obj_in, dict):
            update_data = obj_in
        elif hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = vars(obj_in)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        persist_sync_changes(db)
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: Any) -> ModelType | None:
        obj = db.get(self.model, id)
        if obj:
            db.delete(obj)
            persist_sync_changes(db)
        return obj

    def count(self, db: Session) -> int:
        stmt = select(func.count()).select_from(self.model)
        return db.scalar(stmt) or 0

    async def async_create(self, db, *, obj_in: CreateSchemaType) -> ModelType:
        if isinstance(obj_in, dict):
            create_data = obj_in
        elif hasattr(obj_in, "model_dump"):
            create_data = obj_in.model_dump(exclude_unset=True)
        else:
            create_data = vars(obj_in)
        db_obj = self.model(**create_data)
        db.add(db_obj)
        await persist_changes(db)
        await db.refresh(db_obj)
        return db_obj


from sqlalchemy.ext.asyncio import AsyncSession


class AsyncBaseRepository[
    ModelType: Base,
    CreateSchemaType: BaseModel | dict[str, Any],
    UpdateSchemaType: BaseModel | dict[str, Any],
]:
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        return await db.get(self.model, id)

    async def get_multi(
            self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        stmt = select(self.model).offset(skip).limit(limit)
        result = await db.scalars(stmt)
        return result.all()

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        if isinstance(obj_in, dict):
            create_data = obj_in
        elif hasattr(obj_in, "model_dump"):
            create_data = obj_in.model_dump(exclude_unset=True)
        else:
            create_data = vars(obj_in)
        db_obj = self.model(**create_data)
        db.add(db_obj)
        await persist_changes(db)
        await db.refresh(db_obj)
        return db_obj

    async def update(
            self,
            db: AsyncSession,
            *,
            db_obj: ModelType,
            obj_in: UpdateSchemaType | dict[str, Any]
    ) -> ModelType:
        if isinstance(obj_in, dict):
            update_data = obj_in
        elif hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = vars(obj_in)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        await persist_changes(db)
        await db.refresh(db_obj)
        return db_obj

    async def remove(self, db: AsyncSession, *, id: Any) -> ModelType | None:
        obj = await db.get(self.model, id)
        if obj:
            await db.delete(obj)
            await persist_changes(db)
        return obj

    async def count(self, db: AsyncSession) -> int:
        stmt = select(func.count()).select_from(self.model)
        return (await db.scalar(stmt)) or 0
