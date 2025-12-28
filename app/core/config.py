import os
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SPE - Sistema de Ponto Eletrônico"
    API_V1_STR: str = "/api/v1"
    TIMEZONE: str = "America/Fortaleza"
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./spe.db"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FIRST_SUPERUSER: str
    FIRST_SUPERUSER_PASSWORD: str
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    UPLOAD_DIR: str = "uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


try:
    settings = Settings()
except Exception:
    settings = Settings(
        SECRET_KEY="insecure-default-key-change-this-in-production",
        FIRST_SUPERUSER="admin",
        FIRST_SUPERUSER_PASSWORD="adminpassword",
        BACKEND_CORS_ORIGINS=["*"]
    )

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
