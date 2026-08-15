from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.domain.enums import DeviceKeyType, UserRole
from app.features.devices.device_models import DeviceCredential
from app.features.users.user_models import User
from app.main import app


@pytest.fixture
def mock_maintainer_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MAINTAINER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_maintainer_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_create_credential_endpoint(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 10, 0, 0)
    mock_dev = DeviceCredential(
        id=1,
        name="Device 1",
        key_type=DeviceKeyType.DEVICE,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch(
        "app.features.devices.device_router.device_credential_service.create",
        return_value=mock_dev,
    )

    response = client.post(
        "/api/v1/device-credentials/",
        json={"name": "Device 1", "key_type": "DEVICE", "api_key": "abc12345"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Device 1"


def test_list_credentials_endpoint(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 10, 0, 0)
    mock_dev = DeviceCredential(
        id=1,
        name="Device 1",
        key_type=DeviceKeyType.DEVICE,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch(
        "app.features.devices.device_router.device_credential_service.get_all",
        return_value=[mock_dev],
    )

    response = client.get("/api/v1/device-credentials/")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_update_credential_endpoint(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 10, 0, 0)
    mock_dev = DeviceCredential(
        id=1,
        name="Device Updated",
        key_type=DeviceKeyType.DEVICE,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch(
        "app.features.devices.device_router.device_credential_service.update",
        return_value=mock_dev,
    )

    response = client.put(
        "/api/v1/device-credentials/1",
        json={"name": "Device Updated"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Device Updated"


def test_delete_credential_endpoint(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_router.device_credential_service.delete",
        return_value={"status": "success"},
    )

    response = client.delete("/api/v1/device-credentials/1")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
