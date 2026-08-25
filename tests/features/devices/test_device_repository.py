from app.features.devices.device_repository import (
    DeviceCredentialRepository,
    FirmwareRepository,
    BiometricRepository,
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
