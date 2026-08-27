import io
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_schemas import FirmwareListResponse, FirmwareResponse
from app.features.devices.firmware_service import FirmwareService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import DeviceKeyType, UserRole


@pytest.fixture
def mock_maintainer_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MAINTAINER
    user.is_active = True
    return user


@pytest.fixture
def mock_device() -> DeviceCredential:
    device = MagicMock(spec=DeviceCredential)
    device.id = 1
    device.key_type = DeviceKeyType.DEVICE
    device.is_active = True
    return device


@pytest.fixture
def client(mock_maintainer_user: User, mock_device: DeviceCredential, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.verify_device_api_key] = lambda: mock_device
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_list_firmwares(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        FirmwareListResponse(
            version="1.0.0",
            file_path="uploads/firmware_1.0.0.bin",
            created_at=datetime(2026, 8, 14, 10, 0, 0),
        )
    ]
    mocker.patch.object(
        FirmwareService,
        "get_all_firmwares",
        return_value=expected,
    )

    response = client.get("/api/v1/firmware/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["version"] == "1.0.0"


def test_upload_firmware(client: TestClient, mocker: MagicMock) -> None:
    expected = FirmwareResponse(
        version="1.0.0",
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        FirmwareService,
        "upload_firmware",
        return_value=expected,
    )

    test_file = io.BytesIO(b"firmware binary")
    response = client.post(
        "/api/v1/firmware/upload",
        data={"version": "1.0.0"},
        files={"file": ("firmware.bin", test_file, "application/octet-stream")},
    )
    assert response.status_code == 201
    assert response.json()["version"] == "1.0.0"


def test_update_firmware(client: TestClient, mocker: MagicMock) -> None:
    expected = FirmwareResponse(
        version="1.0.0",
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        FirmwareService,
        "update_firmware_file",
        return_value=expected,
    )

    test_file = io.BytesIO(b"firmware binary updated")
    response = client.put(
        "/api/v1/firmware/1.0.0",
        files={"file": ("firmware.bin", test_file, "application/octet-stream")},
    )
    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"


def test_check_firmware(client: TestClient, mocker: MagicMock) -> None:
    expected = FirmwareResponse(
        version="1.0.1",
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        FirmwareService,
        "get_latest_firmware",
        return_value=expected,
    )

    response = client.get("/api/v1/firmware/check")
    assert response.status_code == 200
    assert response.json()["version"] == "1.0.1"


def test_download_firmware(client: TestClient, mocker: MagicMock) -> None:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"firmware download payload")
        temp_path = f.name

    try:
        mocker.patch.object(
            FirmwareService,
            "get_firmware_file",
            return_value=temp_path,
        )

        response = client.get("/api/v1/firmware/download?version=1.0.0")
        assert response.status_code == 200
        assert response.content == b"firmware download payload"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
