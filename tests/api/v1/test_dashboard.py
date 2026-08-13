from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.main import app
from app.schemas.report import ManagerDashboardResponse, TeamHoursResponse


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
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_manager_dashboard(client: TestClient, mocker: MagicMock) -> None:
    expected = ManagerDashboardResponse(
        full_name="Manager Name",
        next_punch_type="ENTRY",
        today_punches=[],
        total_system_anomalies=0,
        total_pending_adjustments=1,
        today_total_punches=5,
        team_hours=TeamHoursResponse(
            month=8,
            year=2026,
            team_total_hours=160.0,
            team_formatted_time="160:00",
            employees=[],
        ),
    )
    mocker.patch(
        "app.api.v1.dashboard.dashboard_service.get_manager_dashboard",
        return_value=expected,
    )

    response = client.get("/api/v1/dashboard/manager")
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Manager Name"
    assert data["total_pending_adjustments"] == 1
