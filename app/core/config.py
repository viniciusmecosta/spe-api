import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):
    PROJECT_NAME: str
    APP_VERSION: str
    API_V1_STR: str
    TIMEZONE: str
    SQLALCHEMY_DATABASE_URI: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    FIRST_SUPERUSER: str
    FIRST_SUPERUSER_PASSWORD: str
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    DEVICE_API_KEY: str
    UPLOAD_DIR: str
    EXCLUDED_EMPLOYEE_IDS: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    EMAIL_TO: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()

if not os.path.isabs(settings.UPLOAD_DIR):
    settings.UPLOAD_DIR = os.path.join(ROOT_DIR, settings.UPLOAD_DIR)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
