from datetime import date
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.holidays.holiday_models import Holiday
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def mock_manager_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MANAGER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_manager_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_manager] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_create_holiday_endpoint(client: TestClient, mocker: MagicMock) -> None:
    expected = Holiday(id=1, name="Tiradentes", date=date(2026, 4, 21))
    mocker.patch(
        "app.features.holidays.holiday_router.holiday_service.create_holiday",
        return_value=expected,
    )

    response = client.post("/api/v1/holidays/", json={"name": "Tiradentes", "date": "2026-04-21"})
    assert response.status_code == 201
    assert response.json()["name"] == "Tiradentes"


def test_read_holidays_endpoint(client: TestClient, mocker: MagicMock) -> None:
    expected = [Holiday(id=1, name="Tiradentes", date=date(2026, 4, 21))]
    mocker.patch(
        "app.features.holidays.holiday_router.holiday_service.get_all_holidays",
        return_value=expected,
    )

    response = client.get("/api/v1/holidays/")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_delete_holiday_endpoint(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.holidays.holiday_router.holiday_service.delete_holiday",
        return_value={"status": "success"},
    )

    response = client.delete("/api/v1/holidays/1")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
