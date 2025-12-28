import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.domain.models.enums import UserRole
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate

# Removido import desnecessário de get_password_hash aqui, pois o repo já faz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    username = settings.FIRST_SUPERUSER.lower()
    user = user_repository.get_by_username(db, username=username)
    if not user:
        logger.info(f"Creating initial superuser: {username}")

        # CORREÇÃO: Passamos a senha em texto puro (raw).
        # O UserCreate/UserRepository agora se encarrega de fazer o hash.
        user_in = UserCreate(
            name="Mantenedor do Sistema",
            username=username,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            role=UserRole.MAINTAINER,
            is_active=True
        )

        user_repository.create(db, user_in)

        logger.info("Initial maintainer created successfully.")
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
