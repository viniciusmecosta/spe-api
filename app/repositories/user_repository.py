from typing import Any
from sqlalchemy.orm import Session
from app.domain.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserRepository:
    def get_by_username(self, db: Session, username: str) -> User | None:
        return db.query(User).filter(User.username == username).first()

    def get(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> list[User]:
        return db.query(User).offset(skip).limit(limit).all()

    def get_active_users(self, db: Session) -> list[User]:
        return db.query(User).filter(User.is_active == True).all()

    def count_active(self, db: Session) -> int:
        return db.query(User).filter(User.is_active == True).count()

    def create(self, db: Session, user_in: UserCreate) -> User:
        # Nota: create agora espera que schedules sejam tratados pelo service ou
        # se passados aqui, precisam ser tratados.
        # Simplificação: Cria apenas o User, schedules devem ser adicionados via service ou lógica extra.
        # O UserCreate schema pode conter schedules, mas o Model User não aceita no construtor direto se não mapeado.

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
        return db_user

    def update(self, db: Session, db_obj: User, obj_in: UserUpdate | dict) -> User:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True, exclude={'schedules'})

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


user_repository = UserRepository()