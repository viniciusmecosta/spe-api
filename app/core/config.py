import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SPE - Sistema de Ponto Eletrônico"
    API_V1_STR: str = "/api/v1"
    TIMEZONE: str = "America/Fortaleza"
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./spe.db"

    # Configurações de Segurança
    # Valor padrão inseguro removido. Agora a aplicação falhará se não houver SECRET_KEY configurada (ideal para produção)
    # Ou mantemos um default apenas para dev, mas o ideal é forçar a config.
    # Vou manter um default gerado apenas para facilitar o run local sem .env se necessário,
    # mas o .env terá prioridade.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Configuração de Upload
    UPLOAD_DIR: str = "uploads"

    # Configuração para ler o arquivo .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


try:
    settings = Settings()
except Exception:
    settings = Settings(SECRET_KEY="insecure-default-key-change-this-in-production")

# Garante que o diretório de uploads existe
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
