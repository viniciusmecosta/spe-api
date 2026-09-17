from app.core.config import Settings


def test_config_settings_initialization():
    s = Settings(
        PROJECT_NAME="SPE",
        APP_VERSION="1.2.0",
        ENVIRONMENT="test",
        TIMEZONE="America/Fortaleza",
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@localhost/db",
        SECRET_KEY="secret",
        ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=60,
        FIRST_SUPERUSER="admin",
        FIRST_SUPERUSER_PASSWORD="pass",
        BACKEND_CORS_ORIGINS=["http://localhost"],
        UPLOAD_DIR="uploads",
        TELEGRAM_MAX_MESSAGE_LENGTH=4000,
        ROUTINE_LOG_RETENTION_DAYS=30,
        DAILY_REPORT_HOUR=6,
        HOURLY_BACKUP_START_HOUR=0,
        HOURLY_BACKUP_END_HOUR=23,
    )
    assert s.PROJECT_NAME == "SPE"
    assert s.ENVIRONMENT == "test"


def test_cors_origins_validator_string():
    res = Settings.assemble_cors_origins("http://localhost, http://example.com", None)
    assert res == ["http://localhost", "http://example.com"]
