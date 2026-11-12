from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core import config_validation

ROOT_DIR = config_validation.ROOT_DIR

NonBlank = Annotated[str, AfterValidator(config_validation.require_non_blank)]
AppVersion = Annotated[
    str, AfterValidator(config_validation.require_non_blank), AfterValidator(config_validation.validate_app_version)]
Environment = Annotated[
    str, AfterValidator(config_validation.require_non_blank), AfterValidator(config_validation.validate_environment)]
Timezone = Annotated[
    str, AfterValidator(config_validation.require_non_blank), AfterValidator(config_validation.validate_timezone)]
DatabaseUri = Annotated[
    str, AfterValidator(config_validation.require_non_blank), AfterValidator(config_validation.validate_database_uri)]
SecretKey = Annotated[
    str, AfterValidator(config_validation.require_non_blank), AfterValidator(config_validation.validate_secret_key)]
Algorithm = Annotated[
    str, AfterValidator(config_validation.require_non_blank), AfterValidator(config_validation.validate_algorithm)]
CorsOrigins = Annotated[
    list[str],
    NoDecode,
    BeforeValidator(config_validation.assemble_cors_origins),
    AfterValidator(config_validation.validate_cors_origins),
]
ProxyNetworks = Annotated[list[str], AfterValidator(config_validation.validate_proxy_networks)]
UploadDirectory = Annotated[
    str,
    AfterValidator(config_validation.require_non_blank),
    AfterValidator(config_validation.resolve_upload_dir),
]


class Settings(BaseSettings):
    PROJECT_NAME: NonBlank
    APP_VERSION: AppVersion
    ENVIRONMENT: Environment
    TIMEZONE: Timezone
    SQLALCHEMY_DATABASE_URI: DatabaseUri
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
    BACKGROUND_JOBS_ENABLED: bool = True
    REPROCESS_MAX_DAYS: int = Field(default=3660, ge=1, le=36600)
    REPROCESS_MAX_ITEMS: int = Field(default=100000, ge=1, le=1000000)
    REPROCESS_BATCH_SIZE: int = Field(default=25, ge=1, le=100)
    TRUSTED_PROXY_CIDRS: ProxyNetworks = Field(default_factory=list)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_SECOND: int = Field(default=30, ge=1, le=10000)
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=600, ge=1, le=100000)
    RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE: int = Field(default=60, ge=1, le=100000)
    UPLOAD_LOGO_MAX_BYTES: int = Field(default=5 * 1024 * 1024, ge=1)
    UPLOAD_ATTACHMENT_MAX_BYTES: int = Field(default=10 * 1024 * 1024, ge=1)
    UPLOAD_FIRMWARE_MAX_BYTES: int = Field(default=16 * 1024 * 1024, ge=1)
    UPLOAD_LEGACY_REPORT_MAX_BYTES: int = Field(default=25 * 1024 * 1024, ge=1)
    UPLOAD_LOGO_MAX_DIMENSION: int = Field(default=4096, ge=1)
    UPLOAD_LOGO_MAX_PIXELS: int = Field(default=16000000, ge=1)
    UPLOAD_REQUEST_MAX_BYTES: int = Field(default=32 * 1024 * 1024, ge=1)
    SECRET_KEY: SecretKey
    DOCUMENT_SIGNING_KEY: str = ""
    ALGORITHM: Algorithm
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=365)
    PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES: int = Field(default=10, ge=1, le=30)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(ge=1)
    FIRST_SUPERUSER: str = ""
    FIRST_SUPERUSER_PASSWORD: str = ""
    BACKEND_CORS_ORIGINS: CorsOrigins
    UPLOAD_DIR: UploadDirectory
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    TELEGRAM_MAX_MESSAGE_LENGTH: int = Field(ge=1, le=4096)
    ROUTINE_LOG_RETENTION_DAYS: int = Field(ge=1)
    DAILY_REPORT_HOUR: int = Field(ge=0, le=23)
    HOURLY_BACKUP_START_HOUR: int = Field(ge=0, le=23)
    HOURLY_BACKUP_END_HOUR: int = Field(ge=0, le=23)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()


def _is_environment(name: str) -> bool:
    return settings.ENVIRONMENT.strip().casefold() == name


def is_prod() -> bool:
    return _is_environment("prod")


def is_dev() -> bool:
    return _is_environment("dev")
