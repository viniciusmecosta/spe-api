from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
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
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_available_sensor_indices(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_router.biometric_service.get_available_sensor_indices",
        return_value=[1, 2, 3, 4],
    )

    response = client.get("/api/v1/biometric/available-sensor-indices")
    assert response.status_code == 200
    data = response.json()
    assert data == [1, 2, 3, 4]
