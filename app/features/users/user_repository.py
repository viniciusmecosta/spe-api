from typing import Any

from sqlalchemy import asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, Session

from app.core.security import get_password_hash
from app.database.repository import AsyncBaseRepository, BaseRepository
from app.features.devices.device_models import UserBiometric
from app.features.users.user_models import User
from app.features.users.user_schemas import UserCreate, UserUpdate
from app.shared.enums import UserRole


class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    def __init__(self):
        super().__init__(User)

    def get_by_username(self, db: Session, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return db.scalars(stmt).first()

    def get(self, db: Session, user_id: Any) -> User | None:
        stmt = (
            select(User)
            .options(
                selectinload(User.current_schedules_rel),
                selectinload(User.biometrics),
                selectinload(User.historical_schedules),
            )
            .where(User.id == user_id)
        )
        return db.scalars(stmt).first()

    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        role: str | None = None,
        search: str | None = None,
        order_by: str = "id",
        order_direction: str = "asc",
    ) -> list[User]:
        stmt = select(User).options(
            selectinload(User.current_schedules_rel),
            selectinload(User.biometrics),
            selectinload(User.historical_schedules),
        )
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(or_(User.name.ilike(search_term), User.username.ilike(search_term)))

        order_column = getattr(User, order_by, User.id)
        if order_direction.lower() == "desc":
            stmt = stmt.order_by(desc(order_column))
        else:
            stmt = stmt.order_by(asc(order_column))

        stmt = stmt.offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    def _get_bio_fields(self, bio_data: Any):
        if isinstance(bio_data, dict):
            return bio_data.get("id"), bio_data.get("sensor_index"), bio_data.get("template_data"), bio_data.get("finger_id")
        return getattr(bio_data, "id", None), getattr(bio_data, "sensor_index", None), getattr(bio_data, "template_data", None), getattr(bio_data, "finger_id", None)

    def _validate_sensor_idx(self, db: Session, sensor_idx: int, user_id: int, seen_indices: set):
        if sensor_idx is not None:
            if sensor_idx in seen_indices:
                raise ValueError(f"O index {sensor_idx} duplicado na mesma requisicao.")
            seen_indices.add(sensor_idx)
            stmt = select(UserBiometric).where(
                UserBiometric.sensor_index == sensor_idx,
                UserBiometric.user_id != user_id,
            )
            if db.scalar(select(stmt.exists())):
                raise ValueError("Index ja cadastrada para outro usuario")

    def _update_biometrics(self, db: Session, db_obj: User, biometrics_in: list):
        if biometrics_in is None:
            return

        current_biometrics = {b.id: b for b in db_obj.biometrics}
        new_biometrics_list = []
        seen_indices = set()
        for bio_data in biometrics_in:
            bio_id, sensor_idx, tmpl_data, f_id = self._get_bio_fields(bio_data)
            self._validate_sensor_idx(db, sensor_idx, db_obj.id, seen_indices)

            if bio_id and bio_id in current_biometrics:
                existing = current_biometrics[bio_id]
                existing.sensor_index = sensor_idx
                if tmpl_data is not None:
                    existing.template_data = tmpl_data
                existing.finger_id = f_id
                new_biometrics_list.append(existing)
            else:
                new_bio = UserBiometric(sensor_index=sensor_idx, template_data=tmpl_data, finger_id=f_id)
                new_biometrics_list.append(new_bio)
        db_obj.biometrics = new_biometrics_list

    def update(
        self,
        db: Session,
            *,
        db_obj: User,
        obj_in: UserUpdate | dict[str, Any],
    ) -> User:
        if isinstance(obj_in, dict):
            update_data = dict(obj_in)
        elif hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = vars(obj_in)

        update_data.pop("schedules", None)
        biometrics_in = update_data.pop("biometrics", None)

        if update_data.get("password"):
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        if biometrics_in is not None:
            self._update_biometrics(db, db_obj, biometrics_in)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_active_employees(self, db: Session) -> list[User]:
        stmt = select(User).where(User.is_active.is_(True), User.role == UserRole.EMPLOYEE)
        return list(db.scalars(stmt).all())


user_repository = UserRepository()


class AsyncUserRepository(AsyncBaseRepository[User, UserCreate, UserUpdate]):
    def __init__(self):
        super().__init__(User)

    async def create(
            self, db: AsyncSession, *, obj_in: UserCreate | dict[str, Any]
    ) -> User:
        if isinstance(obj_in, dict):
            create_data = dict(obj_in)
        elif hasattr(obj_in, "model_dump"):
            create_data = obj_in.model_dump(exclude_unset=True)
        else:
            create_data = vars(obj_in)

        create_data.pop("schedules", None)
        biometrics_in = create_data.pop("biometrics", None)

        if create_data.get("password"):
            create_data["password_hash"] = get_password_hash(create_data["password"])
            del create_data["password"]

        db_obj = User(**create_data)
        db.add(db_obj)
        await db.flush()

        if biometrics_in is not None:
            await self._update_biometrics(db, db_obj, biometrics_in)

        await db.commit()
        refreshed = await self.get(db, db_obj.id)
        return refreshed if refreshed else db_obj

    async def get_by_username(self, db: AsyncSession, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await db.scalars(stmt)
        return result.first()

    async def get(self, db: AsyncSession, user_id: Any) -> User | None:
        stmt = (
            select(User)
            .options(
                selectinload(User.current_schedules_rel),
                selectinload(User.biometrics),
                selectinload(User.historical_schedules),
            )
            .where(User.id == user_id)
        )
        result = await db.scalars(stmt)
        return result.first()

    async def get_multi(
            self,
            db: AsyncSession,
            *,
            skip: int = 0,
            after_id: int | None = None,
            limit: int = 100,
            is_active: bool | None = None,
            role: str | None = None,
            search: str | None = None,
            order_by: str = "id",
            order_direction: str = "asc",
    ) -> list[User]:
        stmt = select(User).options(
            selectinload(User.current_schedules_rel),
            selectinload(User.biometrics),
            selectinload(User.historical_schedules),
        )

        if after_id is not None:
            stmt = stmt.where(User.id > after_id)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(or_(User.name.ilike(search_term), User.username.ilike(search_term)))

        order_column = getattr(User, order_by, User.id)
        if order_direction.lower() == "desc":
            stmt = stmt.order_by(desc(order_column))
        else:
            stmt = stmt.order_by(asc(order_column))

        stmt = stmt.limit(limit)
        result = await db.scalars(stmt)
        return list(result.all())

    def _get_bio_fields(self, bio_data: Any):
        if isinstance(bio_data, dict):
            return bio_data.get("id"), bio_data.get("sensor_index"), bio_data.get("template_data"), bio_data.get(
                "finger_id")
        return getattr(bio_data, "id", None), getattr(bio_data, "sensor_index", None), getattr(bio_data,
                                                                                               "template_data",
                                                                                               None), getattr(bio_data,
                                                                                                              "finger_id",
                                                                                                              None)

    async def _validate_sensor_idx(self, db: AsyncSession, sensor_idx: int, user_id: int, seen_indices: set):
        if sensor_idx is not None:
            if sensor_idx in seen_indices:
                raise ValueError(f"O index {sensor_idx} duplicado na mesma requisicao.")
            seen_indices.add(sensor_idx)
            stmt = select(UserBiometric).where(
                UserBiometric.sensor_index == sensor_idx,
                UserBiometric.user_id != user_id,
            )
            exists = await db.scalar(select(stmt.exists()))
            if exists:
                raise ValueError("Index ja cadastrada para outro usuario")

    async def _update_biometrics(self, db: AsyncSession, db_obj: User, biometrics_in: list):
        if biometrics_in is None:
            return

        await db.refresh(db_obj, attribute_names=["biometrics"])
        current_biometrics = {b.id: b for b in db_obj.biometrics}
        new_biometrics_list = []
        seen_indices = set()
        for bio_data in biometrics_in:
            bio_id, sensor_idx, tmpl_data, f_id = self._get_bio_fields(bio_data)
            await self._validate_sensor_idx(db, sensor_idx, db_obj.id, seen_indices)

            if bio_id and bio_id in current_biometrics:
                existing = current_biometrics[bio_id]
                existing.sensor_index = sensor_idx
                if tmpl_data is not None:
                    existing.template_data = tmpl_data
                existing.finger_id = f_id
                new_biometrics_list.append(existing)
            else:
                new_bio = UserBiometric(sensor_index=sensor_idx, template_data=tmpl_data, finger_id=f_id)
                new_biometrics_list.append(new_bio)
        db_obj.biometrics = new_biometrics_list

    async def update(
            self,
            db: AsyncSession,
            *,
            db_obj: User,
            obj_in: UserUpdate | dict[str, Any],
    ) -> User:
        if isinstance(obj_in, dict):
            update_data = dict(obj_in)
        elif hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = vars(obj_in)

        update_data.pop("schedules", None)
        biometrics_in = update_data.pop("biometrics", None)

        if update_data.get("password"):
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        if biometrics_in is not None:
            await self._update_biometrics(db, db_obj, biometrics_in)

        db.add(db_obj)
        await db.commit()
        refreshed = await self.get(db, db_obj.id)
        return refreshed if refreshed else db_obj

    async def get_active_employees(self, db: AsyncSession) -> list[User]:
        stmt = select(User).options(
            selectinload(User.current_schedules_rel),
            selectinload(User.biometrics),
            selectinload(User.historical_schedules)
        ).where(User.is_active.is_(True), User.role == UserRole.EMPLOYEE)
        result = await db.scalars(stmt)
        return list(result.all())


async_user_repository = AsyncUserRepository()
