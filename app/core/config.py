import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):
    PROJECT_NAME: str
    APP_VERSION: str
    ENVIRONMENT: str

    TIMEZONE: str
    SQLALCHEMY_DATABASE_URI: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    FIRST_SUPERUSER: str
    FIRST_SUPERUSER_PASSWORD: str
    BACKEND_CORS_ORIGINS: list[str]
    UPLOAD_DIR: str
    SMTP_HOST: str | None
    SMTP_PORT: int | None
    SMTP_USER: str | None
    SMTP_PASSWORD: str | None
    EMAIL_FROM: str | None

    TELEGRAM_BOT_TOKEN: str | None
    TELEGRAM_CHAT_ID: str | None
    TELEGRAM_MAX_MESSAGE_LENGTH: int

    OPERATION_MODE: str
    CONSUMER_SERVER_URL: str | None
    CONSUMER_API_KEY: str | None

    ROUTINE_LOG_RETENTION_DAYS: int
    DAILY_REPORT_HOUR: int
    HOURLY_BACKUP_START_HOUR: int
    HOURLY_BACKUP_END_HOUR: int

    @property
    def DATABASE_PATH(self) -> str:
        if self.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///"):
            return self.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")
        return "spe.db"

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def assemble_cors_origins(cls, v: list[str], info) -> list[str]:
        if isinstance(v, str):
            v = [i.strip() for i in v.split(",")]
        return v

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
