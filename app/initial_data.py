import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.database.session import SessionLocal
from app.domain.models.enums import UserRole
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    user = user_repository.get_by_email(db, email=settings.FIRST_SUPERUSER)
    if not user:
        logger.info(f"Creating initial superuser: {settings.FIRST_SUPERUSER}")

        hashed_password = get_password_hash(settings.FIRST_SUPERUSER_PASSWORD)

        user_in = UserCreate(
            name="Administrador Inicial",
            email=settings.FIRST_SUPERUSER,
            password=hashed_password,
            role=UserRole.MANAGER,
            weekly_workload_hours=44,
            is_active=True
        )

        user_data = UserCreate(
            name="Administrador Inicial",
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            role=UserRole.MANAGER,
            weekly_workload_hours=44,
            is_active=True
        )

        user_data.password = hashed_password

        user_repository.create(db, user_data)
        logger.info("Initial superuser created successfully.")
    else:
        logger.info(f"Superuser {settings.FIRST_SUPERUSER} already exists. Skipping creation.")


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
