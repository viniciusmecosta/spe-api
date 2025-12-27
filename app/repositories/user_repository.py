from sqlalchemy.orm import Session
from app.domain.models.user import User
from app.schemas.user import UserCreate

class UserRepository:
    def get_by_email(self, db: Session, email: str) -> User | None:
        return db.query(User).filter(User.email == email).first()

    def get(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    def create(self, db: Session, user_in: UserCreate) -> User:
        # A hash da senha deve ser feita no Service antes de chamar o Repository
        db_user = User(
            name=user_in.name,
            email=user_in.email,
            password_hash=user_in.password, # Já deve vir hashada
            role=user_in.role,
            weekly_workload_hours=user_in.weekly_workload_hours,
            is_active=user_in.is_active
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

user_repository = UserRepository()