from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.timesheets.anomaly_service import AnomalyService
from app.features.timesheets.timesheet_schemas import AnomalyResponse
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
def client(mock_manager_user: User) -> TestClient:
    async def override_get_async_db():
        yield AsyncMock()

    app.dependency_overrides[deps.get_current_manager] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_async_db] = override_get_async_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_all_anomalies(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        AnomalyResponse(
            user_id=1,
            user_name="Funcionario",
            date="2026-08-14",
            type="MISSING_PUNCH",
            description="Batida faltante",
            severity="HIGH",
        )
    ]
    mocker.patch.object(
        AnomalyService,
        "get_anomalies_by_month",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.get("/api/v1/anomalies/all?month=8&year=2026")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "MISSING_PUNCH"


def test_get_user_anomalies(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        AnomalyResponse(
            user_id=2,
            user_name="Outro",
            date="2026-08-14",
            type="LATE_ENTRY",
            description="Entrada tardia",
            severity="MEDIUM",
        )
    ]
    mocker.patch.object(
        AnomalyService,
        "get_anomalies_by_month",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.get("/api/v1/anomalies/user/2?month=8&year=2026")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user_id"] == 2
