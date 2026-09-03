from unittest.mock import AsyncMock, MagicMock

import pytest
from app.features.devices.device_credential_service import device_credential_service
from app.features.devices.device_exceptions import DeviceCredentialNotFoundError
from app.features.devices.device_models import DeviceCredential
from app.features.devices.device_schemas import DeviceCredentialCreate, DeviceCredentialUpdate
from app.shared.enums import DeviceKeyType


@pytest.mark.asyncio
async def test_create_device_credential(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_device = DeviceCredential(
        id=1,
        name="Device ESP",
        key_type=DeviceKeyType.DEVICE,
        api_key_hash="hash",
        is_active=True,
    )
    mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.create",
        new_callable=AsyncMock,
        return_value=mock_device,
    )
    audit_mock = mocker.patch("app.features.devices.device_credential_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    payload = DeviceCredentialCreate(
        name="Device ESP",
        key_type=DeviceKeyType.DEVICE,
        api_key="secret123",
    )
    result = await device_credential_service.create(async_db_mock, payload, current_user_id=1)
    assert result.id == 1
    assert result.name == "Device ESP"
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_get_all_device_credentials(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    devices = [DeviceCredential(id=1, name="D1", key_type=DeviceKeyType.DEVICE)]
    mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.get_all",
        new_callable=AsyncMock,
        return_value=devices,
    )

    result = await device_credential_service.get_all(async_db_mock)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_update_device_credential_success(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    device = DeviceCredential(id=1, name="Old Name", is_active=True)
    updated_device = DeviceCredential(id=1, name="New Name", is_active=True)
    mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.get",
        new_callable=AsyncMock,
        return_value=device,
    )
    mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.update",
        new_callable=AsyncMock,
        return_value=updated_device,
    )
    audit_mock = mocker.patch("app.features.devices.device_credential_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_credential_service.update(
        async_db_mock, 1, DeviceCredentialUpdate(name="New Name"), current_user_id=1
    )
    assert result.name == "New Name"
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_update_device_credential_not_found(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.get",
        new_callable=AsyncMock,
        return_value=None,
    )
    payload = DeviceCredentialUpdate(name="New Name")
    with pytest.raises(DeviceCredentialNotFoundError) as exc_info:
        await device_credential_service.update(
            async_db_mock, 99, payload, current_user_id=1
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_device_credential_success(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    device = DeviceCredential(id=1, name="Delete Me", is_active=True)
    mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.get",
        new_callable=AsyncMock,
        return_value=device,
    )
    delete_mock = mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.delete",
        new_callable=AsyncMock,
    )
    audit_mock = mocker.patch("app.features.devices.device_credential_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_credential_service.delete(async_db_mock, 1, current_user_id=1)
    assert result == {"status": "success"}
    delete_mock.assert_called_once_with(async_db_mock, 1)
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_delete_device_credential_not_found(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_credential_service.async_device_credential_repository.get",
        new_callable=AsyncMock,
        return_value=None,
    )

    with pytest.raises(DeviceCredentialNotFoundError) as exc_info:
        await device_credential_service.delete(async_db_mock, 99, current_user_id=1)
    assert exc_info.value.status_code == 404


def test_device_credential_service_repo_property():
    custom_repo = MagicMock()
    original_repo = device_credential_service.repo
    try:
        device_credential_service.repo = custom_repo
        assert device_credential_service.repo == custom_repo
    finally:
        device_credential_service.repo = original_repo
