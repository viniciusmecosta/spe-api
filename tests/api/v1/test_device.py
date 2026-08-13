from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import settings
from app.domain.models.device import DeviceCredential
from app.domain.models.enums import DeviceKeyType, RecordType, UserRole
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


def test_get_device_time_success(client: TestClient, mocker: MagicMock) -> None:
    tz = ZoneInfo(settings.TIMEZONE)
    fixed_time = datetime(2026, 8, 14, 15, 30, 0, tzinfo=tz)
    mocker.patch(
        "app.api.v1.device.trusted_time_service.get_trusted_time",
        return_value=(fixed_time, True)
    )

    response = client.get("/api/v1/device/time")

    assert response.status_code == 200
    data = response.json()
    assert data["unix"] == int(fixed_time.timestamp())
    assert data["formatted"] == "14/08/2026 15:30:00"


def test_register_device_punch_success(client: TestClient, mocker: MagicMock) -> None:
    mock_record = MagicMock()
    mock_record.user.name = "Vinicius Costa"
    mock_record.record_datetime = datetime(2026, 8, 14, 8, 0, 0)
    mock_record.record_type = RecordType.ENTRY

    mocker.patch(
        "app.api.v1.device.punch_service.process_biometric_punch",
        return_value=(True, "Sucesso", mock_record)
    )

    response = client.post("/api/v1/device/punch", json={"sensor_index": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["led"] == "green"
    assert "Vinicius" in data["line1"]
    assert data["line2"] == "08:00"
    assert data["line3"] == "Entrada"
    assert len(data["actions"]["buzzer_melody"]) == 3


def test_register_device_punch_failure(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.api.v1.device.punch_service.process_biometric_punch",
        return_value=(False, "Nao reconhecido", None)
    )

    response = client.post("/api/v1/device/punch", json={"sensor_index": 99})

    assert response.status_code == 200
    data = response.json()
    assert data["led"] == "red"
    assert data["line1"] == "Erro"
    assert data["line2"] == "Nao reconhecido"


def test_register_device_punch_exception(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.api.v1.device.punch_service.process_biometric_punch",
        side_effect=Exception("Database error")
    )

    response = client.post("/api/v1/device/punch", json={"sensor_index": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["led"] == "red"
    assert data["line1"] == "Erro Interno"


def test_verify_manager_no_managers(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch("app.api.v1.device.biometric_repository.get_manager_with_biometric", return_value=[])
    mocker.patch("app.api.v1.device.audit_service.log")

    response = client.post("/api/v1/device/verify-manager", json={"sensor_index": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["is_allowed"] is True
    assert "Nenhum gestor cadastrado" in data["message"]


def test_verify_manager_biometric_not_found(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch("app.api.v1.device.biometric_repository.get_manager_with_biometric", return_value=[MagicMock()])
    mocker.patch("app.api.v1.device.biometric_repository.get_by_sensor_index", return_value=None)
    mocker.patch("app.api.v1.device.audit_service.log")

    response = client.post("/api/v1/device/verify-manager", json={"sensor_index": 99})

    assert response.status_code == 200
    data = response.json()
    assert data["is_allowed"] is False
    assert "Biometria não encontrada" in data["message"]


def test_verify_manager_authorized(client: TestClient, mocker: MagicMock) -> None:
    mock_bio = MagicMock()
    mock_bio.user.id = 2
    mock_bio.user.role = UserRole.MANAGER
    mock_bio.user.is_active = True

    mocker.patch("app.api.v1.device.biometric_repository.get_manager_with_biometric", return_value=[mock_bio])
    mocker.patch("app.api.v1.device.biometric_repository.get_by_sensor_index", return_value=mock_bio)
    mocker.patch("app.api.v1.device.audit_service.log")

    response = client.post("/api/v1/device/verify-manager", json={"sensor_index": 2})

    assert response.status_code == 200
    data = response.json()
    assert data["is_allowed"] is True
    assert "Acesso autorizado" in data["message"]


def test_verify_manager_denied_regular_employee(client: TestClient, mocker: MagicMock) -> None:
    mock_bio = MagicMock()
    mock_bio.user.id = 3
    mock_bio.user.role = UserRole.EMPLOYEE
    mock_bio.user.is_active = True

    mocker.patch("app.api.v1.device.biometric_repository.get_manager_with_biometric", return_value=[MagicMock()])
    mocker.patch("app.api.v1.device.biometric_repository.get_by_sensor_index", return_value=mock_bio)
    mocker.patch("app.api.v1.device.audit_service.log")

    response = client.post("/api/v1/device/verify-manager", json={"sensor_index": 3})

    assert response.status_code == 200
    data = response.json()
    assert data["is_allowed"] is False
    assert "Acesso negado" in data["message"]
