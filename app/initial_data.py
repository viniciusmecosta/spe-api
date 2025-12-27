import logging
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate
from app.domain.models.enums import UserRole
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    # Verifica se já existe algum usuário (para não recriar em restarts)
    user = user_repository.get_by_email(db, email="admin@spe.com")
    if not user:
        logger.info("Creating initial superuser: admin@spe.com")
        user_in = UserCreate(
            name="Administrador Inicial",
            email="admin@spe.com",
            password="adminpassword",  # Em produção, usar env var ou secrets
            role=UserRole.MANAGER,
            weekly_workload_hours=44,
            is_active=True
        )
        # Importante: O repository espera que a senha já venha hasheada se usar o método create cru,
        # mas aqui vamos usar o service ou hashear manualmente.
        # Para simplificar e evitar dependência circular com service, hasheamos aqui.
        from app.core.security import get_password_hash
        user_in.password = get_password_hash(user_in.password)

        user_repository.create(db, user_in)
        logger.info("Initial superuser created successfully.")
    else:
        logger.info("Superuser already exists. Skipping creation.")


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