from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.domain.enums import DeviceKeyType
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_schemas import (
    BuzzerNote,
    DeviceActions,
    FeedbackPayload,
    ManagerVerifyResponse,
    TimeResponsePayload,
)
from app.main import app


@pytest.fixture
def mock_device() -> DeviceCredential:
    device = MagicMock(spec=DeviceCredential)
    device.id = 1
    device.name = "Test ESP32 Device"
    device.key_type = DeviceKeyType.DEVICE
    device.is_active = True
    return device


@pytest.fixture
def client(mock_device: DeviceCredential, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.verify_device_api_key] = lambda: mock_device
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_device_time_endpoint(client: TestClient, mocker: MagicMock) -> None:
    expected_payload = TimeResponsePayload(
        unix=1786718400,
        formatted="14/08/2026 15:30:00",
    )
    mocker.patch(
        "app.features.devices.device_router.device_service.get_device_time",
        return_value=expected_payload,
    )

    response = client.get("/api/v1/device/time")

    assert response.status_code == 200
    data = response.json()
    assert data["unix"] == 1786718400
    assert data["formatted"] == "14/08/2026 15:30:00"


def test_register_device_punch_endpoint(client: TestClient, mocker: MagicMock) -> None:
    expected_payload = FeedbackPayload(
        line1="Vinicius C",
        line2="08:00",
        line3="Entrada",
        led="green",
        actions=DeviceActions(
            buzzer_melody=[
                BuzzerNote(frequency=1500, duration_ms=150),
                BuzzerNote(frequency=0, duration_ms=50),
                BuzzerNote(frequency=2000, duration_ms=300),
            ]
        ),
    )
    mocker.patch(
        "app.features.devices.device_router.device_service.process_punch",
        return_value=expected_payload,
    )

    response = client.post("/api/v1/device/punch", json={"sensor_index": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["led"] == "green"
    assert data["line1"] == "Vinicius C"
    assert data["line2"] == "08:00"
    assert data["line3"] == "Entrada"


def test_verify_manager_access_endpoint(client: TestClient, mocker: MagicMock) -> None:
    expected_payload = ManagerVerifyResponse(
        is_allowed=True,
        message="Acesso autorizado.",
    )
    mocker.patch(
        "app.features.devices.device_router.device_service.verify_manager_access",
        return_value=expected_payload,
    )

    response = client.post("/api/v1/device/verify-manager", json={"sensor_index": 2})

    assert response.status_code == 200
    data = response.json()
    assert data["is_allowed"] is True
    assert data["message"] == "Acesso autorizado."
