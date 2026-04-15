from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session
from typing import List, Optional, Set

from app.core.security import get_password_hash
from app.domain.models.biometric import UserBiometric
from app.domain.models.user import User, WorkSchedule
from app.schemas.user import UserUpdate


class UserRepository:
    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def get(self, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    def get_multi(
            self,
            db: Session,
            skip: int = 0,
            limit: int = 100,
            is_active: Optional[bool] = None,
            role: Optional[str] = None,
            search: Optional[str] = None,
            order_by: str = "id",
            order_direction: str = "asc"
    ) -> List[User]:
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

    def update(self, db: Session, db_obj: User, obj_in: UserUpdate | dict) -> User:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        schedules_in = update_data.pop("schedules", None)
        biometrics_in = update_data.pop("biometrics", None)

        if "password" in update_data and update_data["password"]:
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        if schedules_in is not None:
            db_obj.schedules = []
            for sch_data in schedules_in:
                day = sch_data['day_of_week'] if isinstance(sch_data, dict) else sch_data.day_of_week
                hours = sch_data['daily_hours'] if isinstance(sch_data, dict) else sch_data.daily_hours
                new_sch = WorkSchedule(day_of_week=day, daily_hours=hours)
                db_obj.schedules.append(new_sch)

        if biometrics_in is not None:
            current_biometrics = {b.id: b for b in db_obj.biometrics}
            new_biometrics_list = []
            seen_indices = set()
            for bio_data in biometrics_in:
                bio_id = bio_data.get('id') if isinstance(bio_data, dict) else bio_data.id
                sensor_idx = bio_data.get('sensor_index') if isinstance(bio_data, dict) else bio_data.sensor_index
                tmpl_data = bio_data.get('template_data') if isinstance(bio_data, dict) else bio_data.template_data
                desc = bio_data.get('description') if isinstance(bio_data, dict) else bio_data.description
                f_id = bio_data.get('finger_id') if isinstance(bio_data, dict) else bio_data.finger_id

                if sensor_idx is not None:
                    if sensor_idx in seen_indices:
                        raise ValueError(f"O index {sensor_idx} duplicado na mesma requisicao.")
                    seen_indices.add(sensor_idx)
                    existing_bio = db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_idx,
                                                                  UserBiometric.user_id != db_obj.id).first()
                    if existing_bio:
                        raise ValueError(f"Index ja cadastrada para outro usuario")

                if bio_id and bio_id in current_biometrics:
                    existing = current_biometrics[bio_id]
                    existing.sensor_index = sensor_idx
                    if tmpl_data is not None:
                        existing.template_data = tmpl_data
                    existing.description = desc
                    existing.finger_id = f_id
                    new_biometrics_list.append(existing)
                else:
                    new_bio = UserBiometric(sensor_index=sensor_idx, template_data=tmpl_data, description=desc,
                                            finger_id=f_id)
                    new_biometrics_list.append(new_bio)
            db_obj.biometrics = new_biometrics_list

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


user_repository = UserRepository()
