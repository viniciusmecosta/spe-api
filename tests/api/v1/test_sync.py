import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.domain.models.device import DeviceCredential
from app.domain.models.enums import DeviceKeyType
from app.main import app


@pytest.fixture
def mock_consumer_device() -> DeviceCredential:
    device = MagicMock(spec=DeviceCredential)
    device.id = 1
    device.name = "Consumer Device"
    device.key_type = DeviceKeyType.CONSUMER
    device.is_active = True
    return device


@pytest.fixture
def client(mock_consumer_device: DeviceCredential, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.verify_consumer_api_key] = lambda: mock_consumer_device
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_sync_database_endpoint(client: TestClient, mocker: MagicMock) -> None:
    mock_receive = mocker.patch("app.api.v1.sync.sync_service.receive_database")

    test_file = io.BytesIO(b"fake sqlite db content")
    response = client.post(
        "/api/v1/sync/database",
        files={"file": ("spe.db", test_file, "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    mock_receive.assert_called_once()
