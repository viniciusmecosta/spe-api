import logging
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate
from app.domain.models.enums import UserRole
from app.core.config import settings
from app.core.security import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db(db: Session) -> None:
    # Verifica se já existe o superusuário definido nas configurações
    user = user_repository.get_by_email(db, email=settings.FIRST_SUPERUSER)
    if not user:
        logger.info(f"Creating initial superuser: {settings.FIRST_SUPERUSER}")

        # A senha bruta vem do settings, hash é gerado aqui
        hashed_password = get_password_hash(settings.FIRST_SUPERUSER_PASSWORD)

        user_in = UserCreate(
            name="Administrador Inicial",
            email=settings.FIRST_SUPERUSER,
            password=hashed_password,  # Passamos o hash, pois o repository cria direto
            role=UserRole.MANAGER,
            weekly_workload_hours=44,
            is_active=True
        )

        # Como o UserCreate espera 'password' (string), mas queremos salvar o hash,
        # e o repositório atual (implementado anteriormente) não faz o hash automaticamente no método create cru,
        # ajustamos o objeto antes de persistir ou garantimos que o repositório receba o que espera.
        # O repositório implementado anteriormente espera que a senha já venha tratada ou ele salva direto.
        # Vamos garantir:

        # Hack: O schema UserCreate valida campos, mas o repository usa os campos do schema para criar o Model.
        # Vamos passar a senha original para o UserCreate e substituir pelo hash no objeto de banco manualmente
        # ou ajustar a chamada.
        # Ajuste limpo para o código existente:

        # 1. Instancia UserCreate com senha original (para validação pydantic)
        user_data = UserCreate(
            name="Administrador Inicial",
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            role=UserRole.MANAGER,
            weekly_workload_hours=44,
            is_active=True
        )

        # 2. Substitui pela senha hashada antes de enviar ao repositório
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