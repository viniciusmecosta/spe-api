import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.database.session import SessionLocal
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.repositories.user_repository import user_repository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    username = settings.FIRST_SUPERUSER

    user = user_repository.get_by_username(db, username=username)
    if not user:
        logger.info(f"Creating initial superuser: {username}")

        db_user = User(
            username=username,
            name="Mantenedor do Sistema",
            password_hash=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
            role=UserRole.MAINTAINER,
            is_active=True
        )

        db.add(db_user)
        db.commit()
        logger.info("Initial maintainer created successfully.")
    else:
        logger.info(f"Superuser {username} already exists. Skipping creation.")


def main() -> None:
    logger.info("Creating initial data")
    db = SessionLocal()
    try:
        init_db(db)
    except Exception as e:
        logger.error(f"Error creating initial data: {e}")
        raise e
    finally:
        db.close()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
