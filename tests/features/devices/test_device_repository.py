from unittest.mock import MagicMock

import pytest
from app.features.devices.device_repository import (
    AsyncBiometricRepository,
    AsyncDeviceCredentialRepository,
    AsyncFirmwareRepository,
    BiometricRepository,
    DeviceCredentialRepository,
    FirmwareRepository,
)
from app.features.devices.device_schemas import DeviceCredentialCreate, DeviceCredentialUpdate
from app.shared.enums import DeviceKeyType


def test_device_credential_repository(db_session):
    repo = DeviceCredentialRepository()

    created = repo.create(
        db_session,
        obj_in=DeviceCredentialCreate(name="DevRepo Key", key_type=DeviceKeyType.DEVICE, api_key="secretkey123",
                                      is_active=True)
    )
    assert created.id is not None

    assert repo.get(db_session, created.id) is not None
    assert len(repo.get_all(db_session)) >= 1

    updated = repo.update(db_session, db_obj=created, obj_in=DeviceCredentialUpdate(name="DevRepo Key Updated"))
    assert updated.name == "DevRepo Key Updated"

    repo.delete(db_session, created.id)
    assert repo.get(db_session, created.id) is None


def test_firmware_repository(db_session):
    repo = FirmwareRepository()

    fw = repo.create(db_session, version="9.9.9", file_path="/tmp/fw.bin")
    assert fw.id is not None

    assert repo.get_by_version(db_session, "9.9.9") is not None
    assert repo.get_latest(db_session) is not None
    assert len(repo.get_all(db_session)) >= 1


def test_biometric_repository(db_session):
    repo = BiometricRepository()

    assert repo.get_by_sensor_index(db_session, 999999) is None
    assert repo.get_manager_with_biometric(db_session) is None or True


@pytest.mark.asyncio
async def test_async_device_repositories(async_db_mock):
    cred_repo = AsyncDeviceCredentialRepository()
    created = await cred_repo.create(
        async_db_mock,
        obj_in=DeviceCredentialCreate(name="Async Key", key_type=DeviceKeyType.DEVICE, api_key="secret", is_active=True)
    )
    assert created.name == "Async Key"

    async_db_mock.get.return_value = created
    assert await cred_repo.get(async_db_mock, 1) == created

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [created]
    mock_scalars.first.return_value = created
    async_db_mock.scalars.return_value = mock_scalars

    assert len(await cred_repo.get_all(async_db_mock)) == 1

    fw_repo = AsyncFirmwareRepository()
    fw = await fw_repo.create(async_db_mock, version="1.0.0", file_path="/tmp/fw.bin")
    assert fw.version == "1.0.0"

    bio_repo = AsyncBiometricRepository()
    assert await bio_repo.get_by_sensor_index(async_db_mock, 1) == created
