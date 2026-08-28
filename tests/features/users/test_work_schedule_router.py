from datetime import date
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.users.user_models import User
from app.features.users.user_schemas import BulkWorkScheduleResponse
from app.features.users.user_work_schedule_service import UserWorkScheduleService
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def mock_manager_user() -> User:
    return User(
        id=1,
        name="Manager User",
        username="manager",
        role=UserRole.MANAGER,
        is_active=True,
        email="manager@example.com",
    )


@pytest.fixture
def mock_employee_user() -> User:
    return User(
        id=2,
        name="Employee User",
        username="employee",
        role=UserRole.EMPLOYEE,
        is_active=True,
        email="employee@example.com",
    )


@pytest.fixture
def client(mock_manager_user: User) -> TestClient:
    async def override_get_async_db():
        yield AsyncMock()

    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_current_manager] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_db] = lambda: MagicMock()
    app.dependency_overrides[deps.get_async_db] = override_get_async_db

    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_get_bulk_schedules(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        BulkWorkScheduleResponse(
            valid_from=date(2026, 8, 1),
            valid_until=date(2026, 8, 31),
            users=[],
        )
    ]
    mocker.patch.object(
        UserWorkScheduleService,
        "get_bulk_schedules",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.get("/api/v1/schedules/bulk?month=8&year=2026")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_bulk_schedule_by_dates(client: TestClient, mocker: MagicMock) -> None:
    expected = BulkWorkScheduleResponse(
        valid_from=date(2026, 8, 1),
        valid_until=date(2026, 8, 31),
        users=[],
    )
    mocker.patch.object(
        UserWorkScheduleService,
        "get_bulk_schedule",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.get("/api/v1/schedules/bulk/2026-08-01/2026-08-31")
    assert response.status_code == 200
    assert response.json()["valid_from"] == "2026-08-01"


def test_add_bulk_schedules(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(
        UserWorkScheduleService,
        "bulk_add_schedules",
        new_callable=AsyncMock,
        return_value={"status": "success"},
    )

    response = client.post(
        "/api/v1/schedules/bulk",
        json={
            "valid_from": "2026-08-01",
            "valid_until": "2026-08-31",
            "users": [],
        },
    )
    assert response.status_code == 200


def test_update_bulk_schedules(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(
        UserWorkScheduleService,
        "update_bulk_schedules",
        new_callable=AsyncMock,
        return_value={"status": "success"},
    )

    response = client.put(
        "/api/v1/schedules/bulk/2026-08-01/2026-08-31",
        json={
            "valid_from": "2026-08-01",
            "valid_until": "2026-08-31",
            "users": [],
        },
    )
    assert response.status_code == 200


def test_delete_bulk_schedules(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(
        UserWorkScheduleService,
        "delete_bulk_schedules",
        new_callable=AsyncMock,
        return_value={"status": "success"},
    )

    response = client.delete("/api/v1/schedules/bulk/2026-08-01/2026-08-31")
    assert response.status_code == 200
