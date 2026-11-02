import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import DomainException
from app.features.devices.device_exceptions import (
    FirmwareFileNotFoundError,
    FirmwareNotFoundError,
    FirmwareVersionAlreadyExistsError,
    FirmwareVersionNotGreaterError,
    InvalidFirmwareFileTypeError,
    InvalidFirmwareVersionError,
    NoFirmwareAvailableError,
)
from app.features.devices.device_models import Firmware
from app.features.devices.firmware_service import FirmwareService


@pytest.fixture
def firmware_service():
    return FirmwareService()


@pytest.fixture
def mock_upload_file():
    return UploadFile(filename="test.bin", file=io.BytesIO(b"synthetic firmware"))


def test_parse_version_valid(firmware_service):
    assert firmware_service.parse_version("v1.2.3") == (1, 2, 3)


def test_parse_version_invalid(firmware_service):
    with pytest.raises(ValueError, match="Formato de versão inválido"):
        firmware_service.parse_version("invalid")


@pytest.mark.asyncio
async def test_upload_firmware_success(mocker, firmware_service, async_db_mock, mock_upload_file, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    mocker.patch.object(firmware_service.repo, "get_latest", return_value=None)
    mocker.patch.object(firmware_service.repo, "get_by_version", return_value=None)
    mock_fw = Firmware(id=1, version="v1.0.0", file_path="rel/path", created_at=datetime.now(UTC))
    create = mocker.patch.object(firmware_service.repo, "create", return_value=mock_fw)
    audit = mocker.patch("app.features.devices.firmware_service.audit_service.async_log_change")
    result = await firmware_service.upload_firmware(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert result.version == mock_fw.version
    assert result.file_path == mock_fw.file_path
    assert create.call_args.kwargs["commit"] is False
    path = tmp_path / create.call_args.kwargs["file_path"]
    assert path.read_bytes() == b"synthetic firmware"
    async_db_mock.commit.assert_awaited_once()
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_firmware_invalid_version(firmware_service, async_db_mock, mock_upload_file):
    with pytest.raises(InvalidFirmwareVersionError) as exc:
        await firmware_service.upload_firmware(async_db_mock, "1.0.0", mock_upload_file, 1)
    assert exc.value.status_code == 400
    assert "A versão deve estar no formato vx.x.x" in exc.value.detail


@pytest.mark.asyncio
async def test_upload_firmware_invalid_file_extension(firmware_service, async_db_mock):
    file_mock = MagicMock()
    file_mock.filename = "test.txt"
    with pytest.raises(InvalidFirmwareFileTypeError) as exc:
        await firmware_service.upload_firmware(async_db_mock, "v1.0.0", file_mock, 1)
    assert exc.value.status_code == 400
    assert "Apenas arquivos .bin são permitidos" in exc.value.detail


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
async def test_upload_firmware_version_not_greater(mock_repo, firmware_service, async_db_mock, mock_upload_file):
    latest_fw = Firmware(id=1, version="v1.1.0")
    mock_repo.get_latest = AsyncMock(return_value=latest_fw)
    with pytest.raises(FirmwareVersionNotGreaterError) as exc:
        await firmware_service.upload_firmware(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert exc.value.status_code == 400
    assert "estritamente maior" in exc.value.detail


@pytest.mark.asyncio
async def test_upload_firmware_latest_invalid_version(mocker, firmware_service, async_db_mock, mock_upload_file,
                                                       tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    mocker.patch.object(firmware_service.repo, "get_latest", return_value=Firmware(id=1, version="invalid"))
    mocker.patch.object(firmware_service.repo, "get_by_version", return_value=None)
    mocker.patch.object(firmware_service.repo, "create", return_value=Firmware(id=2, version="v1.0.0", created_at=datetime.now(UTC)))
    mocker.patch("app.features.devices.firmware_service.audit_service.async_log_change")
    result = await firmware_service.upload_firmware(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert result.version == "v1.0.0"


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
async def test_upload_firmware_version_exists(mock_repo, firmware_service, async_db_mock, mock_upload_file):
    mock_repo.get_latest = AsyncMock(return_value=None)
    mock_repo.get_by_version = AsyncMock(return_value=Firmware(id=1, version="v1.0.0"))
    with pytest.raises(FirmwareVersionAlreadyExistsError) as exc:
        await firmware_service.upload_firmware(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert exc.value.status_code == 400
    assert "Versão já existe" in exc.value.detail


@pytest.mark.asyncio
async def test_update_firmware_file_invalid_extension(firmware_service, async_db_mock):
    file_mock = MagicMock()
    file_mock.filename = "test.txt"
    with pytest.raises(InvalidFirmwareFileTypeError) as exc:
        await firmware_service.update_firmware_file(async_db_mock, "v1.0.0", file_mock, 1)
    assert exc.value.status_code == 400
    assert "Apenas arquivos .bin são permitidos" in exc.value.detail


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
async def test_update_firmware_file_not_found(mock_repo, firmware_service, async_db_mock, mock_upload_file):
    mock_repo.get_by_version = AsyncMock(return_value=None)
    with pytest.raises(FirmwareNotFoundError) as exc:
        await firmware_service.update_firmware_file(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert exc.value.status_code == 404
    assert "Firmware versão 'v1.0.0' não encontrado." in exc.value.detail


@pytest.mark.asyncio
async def test_update_firmware_file_success(mocker, firmware_service, async_db_mock, mock_upload_file, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    old_fw = Firmware(id=1, version="v1.0.0", file_path="old/path")
    mocker.patch.object(firmware_service.repo, "get_by_version", return_value=old_fw)
    new_fw = Firmware(id=2, version="v1.0.0", created_at=datetime.now(UTC))
    create = mocker.patch.object(firmware_service.repo, "create", return_value=new_fw)
    mocker.patch("app.features.devices.firmware_service.audit_service.async_log_change")
    result = await firmware_service.update_firmware_file(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert result.version == new_fw.version
    assert (tmp_path / create.call_args.kwargs["file_path"]).read_bytes() == b"synthetic firmware"
    async_db_mock.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_firmware_failed_commit_removes_new_binary(mocker, firmware_service, async_db_mock, mock_upload_file,
                                                       tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    mocker.patch.object(firmware_service.repo, "get_latest", return_value=None)
    mocker.patch.object(firmware_service.repo, "get_by_version", return_value=None)
    mocker.patch.object(firmware_service.repo, "create", return_value=Firmware(id=1, version="v1.0.0", created_at=datetime.now(UTC)))
    async_db_mock.commit.side_effect = RuntimeError("commit failed")
    async_db_mock.rollback = AsyncMock()
    with pytest.raises(RuntimeError, match="commit failed"):
        await firmware_service.upload_firmware(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert list((tmp_path / "firmware").iterdir()) == []
    async_db_mock.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_firmware_oversized_upload_never_creates_record(mocker, firmware_service, async_db_mock,
                                                             mock_upload_file, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    mocker.patch.object(settings, "UPLOAD_FIRMWARE_MAX_BYTES", 5)
    mocker.patch.object(firmware_service.repo, "get_latest", return_value=None)
    mocker.patch.object(firmware_service.repo, "get_by_version", return_value=None)
    create = mocker.patch.object(firmware_service.repo, "create")
    with pytest.raises(DomainException) as error:
        await firmware_service.upload_firmware(async_db_mock, "v1.0.0", mock_upload_file, 1)
    assert error.value.status_code == 413
    create.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
async def test_get_latest_firmware_not_found(mock_repo, firmware_service, async_db_mock):
    mock_repo.get_latest = AsyncMock(return_value=None)
    with pytest.raises(NoFirmwareAvailableError) as exc:
        await firmware_service.get_latest_firmware(async_db_mock)
    assert exc.value.status_code == 404
    assert "Nenhum firmware disponível" in exc.value.detail


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
async def test_get_latest_firmware_success(mock_repo, firmware_service, async_db_mock):
    latest_fw = Firmware(id=1, version="v1.0.0")
    mock_repo.get_latest = AsyncMock(return_value=latest_fw)
    result = await firmware_service.get_latest_firmware(async_db_mock)
    assert result == latest_fw


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
async def test_get_all_firmwares(mock_repo, firmware_service, async_db_mock):
    fw_list = [Firmware(id=1, version="v1.0.0")]
    mock_repo.get_all = AsyncMock(return_value=fw_list)
    result = await firmware_service.get_all_firmwares(async_db_mock)
    assert result == fw_list


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
async def test_get_firmware_file_not_found_db(mock_repo, firmware_service, async_db_mock):
    mock_repo.get_by_version = AsyncMock(return_value=None)
    with pytest.raises(FirmwareNotFoundError) as exc:
        await firmware_service.get_firmware_file(async_db_mock, "v1.0.0")
    assert exc.value.status_code == 404
    assert "Firmware versão 'v1.0.0' não encontrado." in exc.value.detail


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
@patch("os.path.exists", return_value=False)
async def test_get_firmware_file_not_found_fs(mock_exists, mock_repo, firmware_service, async_db_mock):
    mock_repo.get_by_version = AsyncMock(return_value=Firmware(id=1, version="v1.0.0", file_path="rel/path"))
    with pytest.raises(FirmwareFileNotFoundError) as exc:
        await firmware_service.get_firmware_file(async_db_mock, "v1.0.0")
    assert exc.value.status_code == 404
    assert "Arquivo do firmware 'v1.0.0' não encontrado no servidor" in exc.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize('stored', ['uploads/firmware/test.bin', 'C:/old/uploads/firmware/test.bin'])
async def test_get_firmware_file_only_resolves_inside_uploads(stored, firmware_service, async_db_mock, mocker, tmp_path):
    mocker.patch('app.core.config.settings.UPLOAD_DIR', str(tmp_path))
    directory = tmp_path / 'firmware'
    directory.mkdir()
    binary = directory / 'test.bin'
    binary.write_bytes(b'synthetic firmware')
    mocker.patch.object(firmware_service.repo, 'get_by_version', new_callable=AsyncMock,
                        return_value=Firmware(id=1, version='v1.0.0', file_path=stored))
    assert await firmware_service.get_firmware_file(async_db_mock, 'v1.0.0') == str(binary)


def test_firmware_service_repo_property(firmware_service):
    custom_repo = MagicMock()
    original_repo = firmware_service.repo
    try:
        firmware_service.repo = custom_repo
        assert firmware_service.repo == custom_repo
    finally:
        firmware_service.repo = original_repo
