from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.domain.models.user import User, WorkSchedule
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import audit_service


class UserService:
    def create_user(self, db: Session, user_in: UserCreate, current_user_id: int) -> User:
        user = user_repository.get_by_username(db, username=user_in.username)
        if user:
            raise HTTPException(
                status_code=400,
                detail="The user with this username already exists.",
            )

        schedules_in = getattr(user_in, 'schedules', None)

        password_hash = get_password_hash(user_in.password)

        db_user = User(
            name=user_in.name,
            username=user_in.username,
            password_hash=password_hash,
            role=user_in.role,
            is_active=user_in.is_active,
            can_manual_punch=user_in.can_manual_punch,
            can_export_report=user_in.can_export_report
        )

        if schedules_in:
            for sch in schedules_in:
                if sch.daily_hours < 0 or sch.daily_hours > 24:
                    raise HTTPException(status_code=400, detail="Daily hours must be between 0 and 24")

                db_sch = WorkSchedule(
                    day_of_week=sch.day_of_week,
                    daily_hours=sch.daily_hours
                )
                db_user.schedules.append(db_sch)

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        audit_service.log(
            db, actor_id=current_user_id, target_user_id=db_user.id, action="CREATE",
            entity="USER", entity_id=db_user.id,
            new_data={
                "username": db_user.username,
                "role": db_user.role,
                "name": db_user.name
            }
        )
        return db_user

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user_in.username and user_in.username != user.username:
            existing = user_repository.get_by_username(db, username=user_in.username)
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists.")

        update_data = user_in.model_dump(exclude_unset=True)
        schedules_in = update_data.pop("schedules", None)

        if "password" in update_data and update_data["password"]:
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        old_data = {
            "username": user.username,
            "role": user.role,
            "name": user.name,
            "is_active": user.is_active
        }

        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)

        if schedules_in is not None:
            user.schedules.clear()
            for sch_data in schedules_in:
                daily_hours = sch_data['daily_hours'] if isinstance(sch_data, dict) else sch_data.daily_hours
                day_of_week = sch_data['day_of_week'] if isinstance(sch_data, dict) else sch_data.day_of_week

                if daily_hours < 0 or daily_hours > 24:
                    raise HTTPException(status_code=400, detail="Daily hours must be between 0 and 24")

                new_sch = WorkSchedule(day_of_week=day_of_week, daily_hours=daily_hours)
                user.schedules.append(new_sch)

        db.add(user)
        db.commit()
        db.refresh(user)

        new_data = {
            "username": user.username,
            "role": user.role,
            "name": user.name,
            "is_active": user.is_active
        }

        audit_service.log(
            db, actor_id=current_user_id, target_user_id=user.id, action="UPDATE",
            entity="USER", entity_id=user.id,
            old_data=old_data, new_data=new_data
        )
        return user

    def disable_user(self, db: Session, user_id: int, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_data = {"is_active": user.is_active}

        user.is_active = False
        db.add(user)
        db.commit()
        db.refresh(user)

        audit_service.log(
            db, actor_id=current_user_id, target_user_id=user.id, action="DISABLE",
            entity="USER", entity_id=user.id,
            old_data=old_data, new_data={"is_active": False}
        )
        return user


user_service = UserService()
