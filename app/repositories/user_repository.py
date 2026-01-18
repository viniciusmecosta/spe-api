from typing import List, Optional
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.domain.models.user import User, WorkSchedule
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

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

user_repository = UserRepository()