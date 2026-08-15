from unittest.mock import MagicMock

from fastapi import HTTPException

import pytest
from app.shared.enums import DeviceKeyType
from app.features.devices.device_credential_service import device_credential_service
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_schemas import DeviceCredentialCreate, DeviceCredentialUpdate


def test_create_device_credential(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mock_device = DeviceCredential(
        id=1,
        name="Device ESP",
        key_type=DeviceKeyType.DEVICE,
        api_key_hash="hash",
        is_active=True,
    )
    mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.create",
        return_value=mock_device,
    )
    audit_mock = mocker.patch("app.features.devices.device_credential_service.audit_service.log")

    payload = DeviceCredentialCreate(
        name="Device ESP",
        key_type=DeviceKeyType.DEVICE,
        api_key="secret123",
    )
    result = device_credential_service.create(db_session_mock, payload, current_user_id=1)
    assert result.id == 1
    assert result.name == "Device ESP"
    audit_mock.assert_called_once()


def test_get_all_device_credentials(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    devices = [DeviceCredential(id=1, name="D1", key_type=DeviceKeyType.DEVICE)]
    mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.get_all",
        return_value=devices,
    )

    result = device_credential_service.get_all(db_session_mock)
    assert len(result) == 1


def test_update_device_credential_success(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    device = DeviceCredential(id=1, name="Old Name", is_active=True)
    updated_device = DeviceCredential(id=1, name="New Name", is_active=True)
    mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.get",
        return_value=device,
    )
    mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.update",
        return_value=updated_device,
    )
    audit_mock = mocker.patch("app.features.devices.device_credential_service.audit_service.log")

    result = device_credential_service.update(
        db_session_mock, 1, DeviceCredentialUpdate(name="New Name"), current_user_id=1
    )
    assert result.name == "New Name"
    audit_mock.assert_called_once()


def test_update_device_credential_not_found(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.get",
        return_value=None,
    )
    payload = DeviceCredentialUpdate(name="New Name")
    with pytest.raises(HTTPException) as exc_info:
        device_credential_service.update(
            db_session_mock, 99, payload, current_user_id=1
        )
    assert exc_info.value.status_code == 404


def test_delete_device_credential_success(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    device = DeviceCredential(id=1, name="Delete Me", is_active=True)
    mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.get",
        return_value=device,
    )
    delete_mock = mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.delete"
    )
    audit_mock = mocker.patch("app.features.devices.device_credential_service.audit_service.log")

    result = device_credential_service.delete(db_session_mock, 1, current_user_id=1)
    assert result == {"status": "success"}
    delete_mock.assert_called_once_with(db_session_mock, 1)
    audit_mock.assert_called_once()


def test_delete_device_credential_not_found(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_credential_service.device_credential_repository.get",
        return_value=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        device_credential_service.delete(db_session_mock, 99, current_user_id=1)
    assert exc_info.value.status_code == 404
