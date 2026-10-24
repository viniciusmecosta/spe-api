from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    PROJECT_NAME: str
    APP_VERSION: str
    ENVIRONMENT: str

    TIMEZONE: str
    SQLALCHEMY_DATABASE_URI: str
    POSTGRES_DB: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=5, ge=0, le=100)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=15, ge=1, le=120)
    DB_CONNECT_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=120)
    DB_STATEMENT_TIMEOUT_MS: int = Field(default=120000, ge=1000, le=3600000)
    DB_LOCK_TIMEOUT_MS: int = Field(default=10000, ge=100, le=300000)
    DB_IDLE_TRANSACTION_TIMEOUT_MS: int = Field(default=60000, ge=1000, le=3600000)
    REPROCESS_MAX_DAYS: int = Field(default=3660, ge=1, le=36600)
    REPROCESS_MAX_ITEMS: int = Field(default=100000, ge=1, le=1000000)
    REPROCESS_BATCH_SIZE: int = Field(default=25, ge=1, le=100)
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    FIRST_SUPERUSER: str
    FIRST_SUPERUSER_PASSWORD: str
    BACKEND_CORS_ORIGINS: list[str]
    UPLOAD_DIR: str
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None

    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    TELEGRAM_MAX_MESSAGE_LENGTH: int

    ROUTINE_LOG_RETENTION_DAYS: int
    DAILY_REPORT_HOUR: int
    HOURLY_BACKUP_START_HOUR: int
    HOURLY_BACKUP_END_HOUR: int

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def assemble_cors_origins(cls, v: list[str] | str, info=None) -> list[str]:
        if isinstance(v, str):
            v = [i.strip() for i in v.split(",")]
        return v

    @field_validator("UPLOAD_DIR")
    @classmethod
    def assemble_upload_dir(cls, v: str) -> str:
        upload_path = Path(v)
        if not upload_path.is_absolute():
            upload_path = ROOT_DIR / upload_path
        return str(upload_path)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()


def _is_environment(name: str) -> bool:
    return settings.ENVIRONMENT.strip().casefold() == name


def is_prod() -> bool:
    return _is_environment("prod")


def is_dev() -> bool:
    return _is_environment("dev")
