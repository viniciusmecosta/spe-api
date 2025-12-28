from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate
from app.domain.models.user import User, WorkSchedule
from app.core.security import get_password_hash
from app.services.audit_service import audit_service


class UserService:
    def create_user(self, db: Session, user_in: UserCreate, current_user_id: int) -> User:
        user = user_repository.get_by_username(db, username=user_in.username)
        if user:
            raise HTTPException(
                status_code=400,
                detail="The user with this username already exists.",
            )

        # Captura os horários antes de manipular o objeto
        schedules_in = user_in.schedules

        user_in.password = get_password_hash(user_in.password)

        # Criação manual do objeto User para evitar passar 'schedules' para o construtor do SQLAlchemy
        # (já que UserCreate tem 'schedules' mas o modelo User não tem esse campo direto no init)
        db_user = User(
            name=user_in.name,
            username=user_in.username,
            password_hash=user_in.password,
            role=user_in.role,
            is_active=user_in.is_active
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        # Agora cria os horários associados, se houver
        if schedules_in:
            for sched in schedules_in:
                db_sched = WorkSchedule(
                    user_id=db_user.id,
                    day_of_week=sched.day_of_week,
                    daily_hours=sched.daily_hours
                )
                db.add(db_sched)
            db.commit()
            db.refresh(db_user)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="CREATE",
            entity="USER",
            entity_id=db_user.id,
            details=f"Created user {db_user.username}"
        )
        return db_user

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user_in.password:
            user_in.password = get_password_hash(user_in.password)

        if user_in.username and user_in.username != user.username:
            existing = user_repository.get_by_username(db, username=user_in.username)
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists.")

        # Update User fields
        user_data = user_in.model_dump(exclude_unset=True, exclude={'schedules'})
        for field, value in user_data.items():
            setattr(user, field, value)

        # Update Schedules if provided
        if user_in.schedules is not None:
            # Remove old
            db.query(WorkSchedule).filter(WorkSchedule.user_id == user.id).delete()
            # Add new
            for sched in user_in.schedules:
                db.add(WorkSchedule(user_id=user.id, day_of_week=sched.day_of_week, daily_hours=sched.daily_hours))

        db.add(user)
        db.commit()
        db.refresh(user)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="UPDATE",
            entity="USER",
            entity_id=user.id,
            details="Updated user profile and/or schedule"
        )
        return user

    def disable_user(self, db: Session, user_id: int, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_active = False
        db.add(user)
        db.commit()
        db.refresh(user)

        audit_service.log(
            db,
            user_id=current_user_id,
            action="DISABLE",
            entity="USER",
            entity_id=user.id,
            details="Disabled user"
        )
        return user


user_service = UserService()