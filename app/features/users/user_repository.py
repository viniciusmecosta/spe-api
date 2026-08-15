from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.features.devices.device_models import UserBiometric
from app.domain.enums import UserRole
from app.features.users.user_models import User
from app.features.users.user_schemas import UserUpdate


class UserRepository:
    def get_by_username(self, db: Session, username: str) -> User | None:
        return db.query(User).filter(User.username == username).first()

    def get(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    def get_multi(
            self,
            db: Session,
            skip: int = 0,
            limit: int = 100,
            is_active: bool | None = None,
            role: str | None = None,
            search: str | None = None,
            order_by: str = "id",
            order_direction: str = "asc"
    ) -> list[User]:
        query = db.query(User)
        if is_active is not None:
            query = query.filter(User.is_active == is_active)
        if role is not None:
            query = query.filter(User.role == role)
        if search:
            search_term = f"%{search}%"
            query = query.filter(or_(User.name.ilike(search_term), User.username.ilike(search_term)))
        order_column = getattr(User, order_by, User.id)
        if order_direction.lower() == "desc":
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(asc(order_column))
        return query.offset(skip).limit(limit).all()

    def _get_bio_fields(self, bio_data):
        if isinstance(bio_data, dict):
            return bio_data.get('id'), bio_data.get('sensor_index'), bio_data.get('template_data'), bio_data.get(
                'finger_id')
        return bio_data.id, bio_data.sensor_index, bio_data.template_data, bio_data.finger_id

    def _validate_sensor_idx(self, db: Session, sensor_idx: int, user_id: int, seen_indices: set):
        if sensor_idx is not None:
            if sensor_idx in seen_indices:
                raise ValueError(f"O index {sensor_idx} duplicado na mesma requisicao.")
            seen_indices.add(sensor_idx)
            existing_bio = db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_idx,
                                                          UserBiometric.user_id != user_id).first()
            if existing_bio:
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

    def update(self, db: Session, db_obj: User, obj_in: UserUpdate | dict) -> User:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        update_data.pop("schedules", None)
        biometrics_in = update_data.pop("biometrics", None)

        if update_data.get("password"):
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        self._update_biometrics(db, db_obj, biometrics_in)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_active_employees(self, db: Session) -> list[User]:
        return db.query(User).filter(User.is_active.is_(True), User.role == UserRole.EMPLOYEE).all()


user_repository = UserRepository()
