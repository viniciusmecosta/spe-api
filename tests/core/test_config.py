import pytest
from pydantic import ValidationError

from app.core.config import Settings, is_dev, is_prod, settings
from app.core.config_validation import assemble_cors_origins, validate_proxy_networks


def test_config_settings_initialization():
    s = Settings(
        PROJECT_NAME="SPE",
        APP_VERSION="1.2.0",
        ENVIRONMENT="test",
        TIMEZONE="America/Fortaleza",
        SQLALCHEMY_DATABASE_URI="postgresql://user:pass@localhost/db",
        SECRET_KEY="s" * 32,
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
    assert s.ENVIRONMENT == "TEST"


def test_cors_origins_validator_string():
    res = assemble_cors_origins("http://localhost, http://example.com")
    assert res == ["http://localhost", "http://example.com"]


def test_environment_helpers(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", " PROD ")
    assert is_prod()
    assert not is_dev()

    monkeypatch.setattr(settings, "ENVIRONMENT", "Dev")
    assert is_dev()
    assert not is_prod()

    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    assert not is_dev()
    assert not is_prod()


def test_validate_proxy_networks():
    assert validate_proxy_networks(["10.0.0.0/8", "192.168.1.1/32"]) == ["10.0.0.0/8", "192.168.1.1/32"]


def valid_settings_data():
    return {
        "PROJECT_NAME": "SPE",
        "APP_VERSION": "2.0.2",
        "ENVIRONMENT": "test",
        "TIMEZONE": "America/Fortaleza",
        "SQLALCHEMY_DATABASE_URI": "postgresql+asyncpg://user:pass@localhost/db",
        "SECRET_KEY": "s" * 32,
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 60,
        "FIRST_SUPERUSER": "admin",
        "FIRST_SUPERUSER_PASSWORD": "long-enough-password",
        "BACKEND_CORS_ORIGINS": ["http://localhost"],
        "UPLOAD_DIR": "uploads",
        "TELEGRAM_MAX_MESSAGE_LENGTH": 4000,
        "ROUTINE_LOG_RETENTION_DAYS": 30,
        "DAILY_REPORT_HOUR": 6,
        "HOURLY_BACKUP_START_HOUR": 0,
        "HOURLY_BACKUP_END_HOUR": 23,
    }


def test_missing_required_settings_fail_initialization():
    values = valid_settings_data()
    values.pop("APP_VERSION")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("APP_VERSION", "2.0"),
        ("ENVIRONMENT", "staging"),
        ("TIMEZONE", "Mars/Olympus"),
        ("SQLALCHEMY_DATABASE_URI", "not-a-database-url"),
        ("SECRET_KEY", "short"),
        ("ALGORITHM", "none"),
        ("BACKEND_CORS_ORIGINS", ["file:///tmp"]),
    ],
)
def test_malformed_settings_fail_initialization(field, value):
    values = valid_settings_data()
    values[field] = value
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_initial_superuser_settings_can_be_empty():
    values = valid_settings_data()
    values["FIRST_SUPERUSER"] = ""
    values["FIRST_SUPERUSER_PASSWORD"] = ""
    result = Settings(_env_file=None, **values)
    assert result.FIRST_SUPERUSER == ""
    assert result.FIRST_SUPERUSER_PASSWORD == ""
