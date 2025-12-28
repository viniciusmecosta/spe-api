from typing import List

from sqlalchemy.orm import Session

from app.domain.models.user import User
from app.schemas.user import UserCreate


class UserRepository:
    def get_by_username(self, db: Session, username: str) -> User | None:
        return db.query(User).filter(User.username == username).first()

    def get(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).offset(skip).limit(limit).all()

    def get_active_users(self, db: Session) -> List[User]:
        return db.query(User).filter(User.is_active == True).all()

    def count_active(self, db: Session) -> int:
        return db.query(User).filter(User.is_active == True).count()

    def create(self, db: Session, user_in: UserCreate) -> User:
        # Mantido para compatibilidade, mas o Service é quem está chamando a criação agora
        # para orquestrar senha e validações.
        # Se for usar direto repository, precisa implementar a mesma lógica do service.
        pass

    def update(self, db: Session, *, db_obj: User, obj_in: dict) -> User:
        # Método genérico de update, caso necessário
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


user_repository = UserRepository()
