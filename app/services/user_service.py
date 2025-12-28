from fastapi import HTTPException, status
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

        # Captura os horários antes de manipular o objeto
        # user_in.schedules é uma lista de objetos Pydantic agora
        schedules_in = user_in.schedules

        user_in.password = get_password_hash(user_in.password)

        db_user = User(
            name=user_in.name,
            username=user_in.username,
            password_hash=user_in.password,
            role=user_in.role,
            is_active=user_in.is_active
        )

        # Adiciona Schedules
        if schedules_in:
            for sch in schedules_in:
                db_sch = WorkSchedule(
                    day_of_week=sch.day_of_week,
                    daily_hours=sch.daily_hours
                )
                db_user.schedules.append(db_sch)

        db.add(db_user)
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

        # Verifica unicidade de username se alterado
        if user_in.username and user_in.username != user.username:
            existing = user_repository.get_by_username(db, username=user_in.username)
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists.")

        update_data = user_in.model_dump(exclude_unset=True)

        # Separa schedules para tratamento manual
        schedules_in = update_data.pop("schedules", None)

        # Atualiza senha se fornecida
        if "password" in update_data and update_data["password"]:
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        # Atualiza campos simples do usuário
        for field, value in update_data.items():
            setattr(user, field, value)

        # Atualização de Schedules (Lógica Corrigida)
        if schedules_in is not None:
            # 1. Limpa a lista existente. O cascade delete-orphan cuidará da remoção no banco.
            user.schedules.clear()

            # 2. Adiciona os novos horários
            for sch_data in schedules_in:
                # sch_data aqui é um dict, pois veio de model_dump()
                new_sch = WorkSchedule(
                    day_of_week=sch_data['day_of_week'],
                    daily_hours=sch_data['daily_hours']
                )
                # Adiciona à relação. O SQLAlchemy vai inserir e associar o ID automaticamente.
                user.schedules.append(new_sch)

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
