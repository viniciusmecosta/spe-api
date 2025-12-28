import logging
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate
from app.domain.models.user import WorkSchedule
from app.domain.models.enums import UserRole
from app.core.config import settings
from app.core.security import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    username = settings.FIRST_SUPERUSER.lower()
    user = user_repository.get_by_username(db, username=username)
    if not user:
        logger.info(f"Creating initial superuser: {username}")

        hashed_password = get_password_hash(settings.FIRST_SUPERUSER_PASSWORD)

        # Cria usuário admin
        user_in = UserCreate(
            name="Administrador Inicial",
            username=username,
            password=hashed_password,
            role=UserRole.MANAGER,
            is_active=True
        )
        user_in.password = hashed_password

        created_user = user_repository.create(db, user_in)

        schedules = []
        for day in range(5):
            schedules.append(WorkSchedule(user_id=created_user.id, day_of_week=day, daily_hours=8.0))

        schedules.append(WorkSchedule(user_id=created_user.id, day_of_week=5, daily_hours=4.0))

        db.add_all(schedules)
        db.commit()

        logger.info("Initial superuser created successfully with default schedule.")
    else:
        logger.info(f"Superuser {username} already exists. Skipping creation.")


def main() -> None:
    logger.info("Creating initial data")
    db = SessionLocal()
    try:
        init_db(db)
    finally:
        db.close()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()