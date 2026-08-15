from datetime import date
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.domain.enums import UserRole
from app.features.users.user_models import User
from app.features.users.user_schemas import BulkWorkScheduleResponse
from app.main import app


@pytest.fixture
def mock_manager_user() -> User:
    user = User(
        id=1,
        name="Manager User",
        username="manager",
        role=UserRole.MANAGER,
        is_active=True,
        email="manager@example.com",
    )
    return user


@pytest.fixture
def mock_employee_user() -> User:
    user = User(
        id=2,
        name="Employee User",
        username="employee",
        role=UserRole.EMPLOYEE,
        is_active=True,
        email="emp@example.com",
    )
    return user


@pytest.fixture
def client(mock_manager_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_manager] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_read_users(client: TestClient, mock_manager_user: User, mocker: MagicMock) -> None:
    mocker.patch("app.features.users.user_router.user_service.get_multi", return_value=[mock_manager_user])

    response = client.get("/api/v1/users/?skip=0&limit=10")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_user(client: TestClient, mock_employee_user: User, mocker: MagicMock) -> None:
    mocker.patch("app.features.users.user_router.user_service.create_user", return_value=mock_employee_user)

    response = client.post(
        "/api/v1/users/",
        json={"name": "Employee User", "username": "employee", "password": "password123"},
    )
    assert response.status_code == 201
    assert response.json()["username"] == "employee"


def test_read_user_me(client: TestClient, mock_manager_user: User, mocker: MagicMock) -> None:
    expected_data = {
        "id": 1,
        "name": "Manager User",
        "username": "manager",
        "role": "MANAGER",
        "is_active": True,
        "email": "manager@example.com",
        "can_manual_punch_desktop": True,
        "can_manual_punch_mobile": True,
    }
    mocker.patch("app.features.users.user_router.user_service.get_user_me", return_value=expected_data)

    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["username"] == "manager"


def test_update_user_me(client: TestClient, mock_manager_user: User, mocker: MagicMock) -> None:
    mocker.patch("app.features.users.user_router.user_service.update_user", return_value=mock_manager_user)

    response = client.put(
        "/api/v1/users/me",
        json={"name": "Manager Updated"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Manager User"


def test_read_user_by_id(client: TestClient, mock_employee_user: User, mocker: MagicMock) -> None:
    mocker.patch("app.features.users.user_router.user_service.get_user_by_id", return_value=mock_employee_user)

    response = client.get("/api/v1/users/2")
    assert response.status_code == 200
    assert response.json()["username"] == "employee"


def test_update_user(client: TestClient, mock_employee_user: User, mocker: MagicMock) -> None:
    mocker.patch("app.features.users.user_router.user_service.update_user_by_admin", return_value=mock_employee_user)

    response = client.put(
        "/api/v1/users/2",
        json={"name": "Employee Updated"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "employee"


def test_get_bulk_schedules(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        BulkWorkScheduleResponse(
            valid_from=date(2026, 8, 1),
            valid_until=date(2026, 8, 31),
            users=[],
        )
    ]
    mocker.patch(
        "app.features.users.user_router.user_work_schedule_service.get_bulk_schedules",
        return_value=expected,
    )

    response = client.get("/api/v1/users/bulk-schedules?month=8&year=2026")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_bulk_schedule_by_dates(client: TestClient, mocker: MagicMock) -> None:
    expected = BulkWorkScheduleResponse(
        valid_from=date(2026, 8, 1),
        valid_until=date(2026, 8, 31),
        users=[],
    )
    mocker.patch(
        "app.features.users.user_router.user_work_schedule_service.get_bulk_schedule",
        return_value=expected,
    )

    response = client.get("/api/v1/users/bulk-schedules/2026-08-01/2026-08-31")
    assert response.status_code == 200
    assert response.json()["valid_from"] == "2026-08-01"


def test_add_bulk_schedules(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.users.user_router.user_work_schedule_service.bulk_add_schedules",
        return_value={"status": "success"},
    )

    response = client.post(
        "/api/v1/users/bulk-schedules",
        json={
            "valid_from": "2026-08-01",
            "valid_until": "2026-08-31",
            "users": [],
        },
    )
    assert response.status_code == 200


def test_delete_bulk_schedules(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.users.user_router.user_work_schedule_service.delete_bulk_schedules",
        return_value={"status": "success"},
    )

    response = client.delete("/api/v1/users/bulk-schedules/2026-08-01/2026-08-31")
    assert response.status_code == 200
