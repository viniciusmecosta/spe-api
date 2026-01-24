from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.security import get_password_hash
from app.domain.models.user import User, WorkSchedule
from app.domain.models.biometric import UserBiometric
from app.schemas.user import UserCreate, UserUpdate


class UserRepository:
    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def get(self, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).offset(skip).limit(limit).all()

    def get_active_users(self, db: Session) -> List[User]:
        return db.query(User).filter(User.is_active == True).all()

    def count_active(self, db: Session) -> int:
        return db.query(User).filter(User.is_active == True).count()

    def create(self, db: Session, user_in: UserCreate) -> User:
        db_user = User(
            username=user_in.username,
            name=user_in.name,
            password_hash=get_password_hash(user_in.password),
            role=user_in.role,
            is_active=user_in.is_active
        )

        if hasattr(user_in, 'schedules') and user_in.schedules:
            for sch in user_in.schedules:
                db_sch = WorkSchedule(
                    day_of_week=sch.day_of_week,
                    daily_hours=sch.daily_hours
                )
                db_user.schedules.append(db_sch)

        if hasattr(user_in, 'biometrics') and user_in.biometrics:
            for bio in user_in.biometrics:
                db_bio = UserBiometric(
                    sensor_index=bio.sensor_index,
                    template_data=bio.template_data,
                    description=bio.description
                )
                db_user.biometrics.append(db_bio)

        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

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
                if isinstance(sch_data, dict):
                    day = sch_data['day_of_week']
                    hours = sch_data['daily_hours']
                else:
                    day = sch_data.day_of_week
                    hours = sch_data.daily_hours

                new_sch = WorkSchedule(day_of_week=day, daily_hours=hours)
                db_obj.schedules.append(new_sch)

        if biometrics_in is not None:
            current_biometrics = {b.id: b for b in db_obj.biometrics}
            incoming_ids = set()
            new_biometrics_list = []

            for bio_data in biometrics_in:
                if isinstance(bio_data, dict):
                    bio_id = bio_data.get('id')
                    sensor_idx = bio_data.get('sensor_index')
                    tmpl_data = bio_data.get('template_data')
                    desc = bio_data.get('description')
                else:
                    bio_id = bio_data.id
                    sensor_idx = bio_data.sensor_index
                    tmpl_data = bio_data.template_data
                    desc = bio_data.description

                if bio_id and bio_id in current_biometrics:
                    incoming_ids.add(bio_id)
                    existing = current_biometrics[bio_id]
                    existing.sensor_index = sensor_idx
                    if tmpl_data is not None:
                        existing.template_data = tmpl_data
                    existing.description = desc
                    new_biometrics_list.append(existing)
                else:
                    new_bio = UserBiometric(
                        sensor_index=sensor_idx,
                        template_data=tmpl_data,
                        description=desc
                    )
                    new_biometrics_list.append(new_bio)

            db_obj.biometrics = new_biometrics_list

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


user_repository = UserRepository()