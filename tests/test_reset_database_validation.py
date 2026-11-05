import pytest

from app.core.config import settings
from scripts.reset_database import reset_database


@pytest.mark.parametrize("uri", [
    "postgresql://user:password@localhost/postgres",
    "postgresql://user:password@localhost/template0",
    "postgresql://user:password@localhost/template1",
    "postgresql://user:password@localhost/",
    "sqlite:///application.db",
])
def test_reset_rejects_non_application_databases(monkeypatch, mocker, uri):
    monkeypatch.setattr(settings, "SQLALCHEMY_DATABASE_URI", uri)
    connect = mocker.patch("scripts.reset_database.psycopg2.connect")
    with pytest.raises(ValueError):
        reset_database()
    connect.assert_not_called()
