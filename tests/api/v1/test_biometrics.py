from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.main import app


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
        "app.api.v1.biometrics.biometric_service.get_available_sensor_indices",
        return_value=[1, 2, 3, 4],
    )

    response = client.get("/api/v1/biometric/available-sensor-indices")
    assert response.status_code == 200
    data = response.json()
    assert data == [1, 2, 3, 4]
