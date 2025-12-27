import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SPE - Sistema de Ponto Eletrônico"
    API_V1_STR: str = "/api/v1"
    TIMEZONE: str = "America/Fortaleza"
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./spe.db"

    # Configurações de Segurança
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Credenciais Iniciais (Lidas do .env)
    FIRST_SUPERUSER: str
    FIRST_SUPERUSER_PASSWORD: str

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
    # Fallback apenas para evitar quebras em ambientes de build sem .env
    # Em produção real, o .env ou variáveis de ambiente devem existir.
    settings = Settings(
        SECRET_KEY="insecure-default-key-change-this-in-production",
        FIRST_SUPERUSER="admin@spe.com",
        FIRST_SUPERUSER_PASSWORD="adminpassword"
    )

# Garante que o diretório de uploads existe
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)