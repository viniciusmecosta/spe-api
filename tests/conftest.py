from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.features.adjustments.adjustment_models
import app.features.companies.company_models
import app.features.devices.device_models
import app.features.holidays.holiday_models
import app.features.payroll.payroll_models
import app.features.printers.printer_models
import app.features.system.system_models
import app.features.time_records.time_record_models
import app.features.users.user_models
from app.database.base import Base
from app.core.config import settings
from app.features.users.user_models import User
from app.features.companies.company_models import Company
from app.shared.enums import UserRole


@pytest.fixture(scope="session", autouse=True)
def cleanup_app_database():
    yield
    from app.database.session import engine
    engine.dispose()


@pytest.fixture
def db_session_mock():
    session = MagicMock(spec=Session)

    class QueryMock:
        def __init__(self, items=None):
            self.items = items or []

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def options(self, *args, **kwargs):
            return self

        def join(self, *args, **kwargs):
            return self

        def outerjoin(self, *args, **kwargs):
            return self

        def offset(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def distinct(self, *args, **kwargs):
            return self

        def group_by(self, *args, **kwargs):
            return self

        def first(self):
            return self.items[0] if self.items else None

        def all(self):
            return self.items

        def delete(self, *args, **kwargs):
            return len(self.items)

    session.query.return_value = QueryMock()
    return session


@pytest.fixture
def mock_get_db_session(mocker, db_session_mock):
    mock = mocker.patch("app.database.session.get_db_session")

    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock.return_value = ContextManagerMock()
    return mock


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def company(db_session):
    comp = Company(name="Test Company", cnpj="44555666000181", address="Rua Teste 123")
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)
    return comp


@pytest.fixture
def normal_user(db_session):
    usr = User(
        username="testuser",
        name="Test User",
        password_hash="hashedpass",
        role=UserRole.EMPLOYEE,
        is_active=True
    )
    db_session.add(usr)
    db_session.commit()
    db_session.refresh(usr)
    return usr


@pytest.fixture
def current_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))
