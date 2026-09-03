from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
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
    with patch("os.makedirs"):
        return FirmwareService()


@pytest.fixture
def mock_upload_file():
    file_mock = MagicMock()
    file_mock.filename = "test.bin"
    file_mock.file = MagicMock()
    return file_mock


def test_init():
    with patch("os.makedirs") as mock_makedirs:
        service = FirmwareService()
        mock_makedirs.assert_called_once_with(service.firmware_dir, exist_ok=True)


def test_parse_version_valid(firmware_service):
    assert firmware_service.parse_version("v1.2.3") == (1, 2, 3)


def test_parse_version_invalid(firmware_service):
    with pytest.raises(ValueError, match="Formato de versão inválido"):
        firmware_service.parse_version("invalid")


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
@patch("app.features.devices.firmware_service.audit_service")
@patch("app.features.devices.firmware_service.time.time", return_value=1234567890)
@patch("builtins.open", new_callable=mock_open)
@patch("shutil.copyfileobj")
async def test_upload_firmware_success(mock_copy, mock_file, mock_time, mock_audit, mock_repo, firmware_service,
                                       async_db_mock, mock_upload_file):
    mock_repo.get_latest = AsyncMock(return_value=None)
    mock_repo.get_by_version = AsyncMock(return_value=None)
    mock_fw = Firmware(id=1, version="v1.0.0", file_path="rel/path")
    mock_repo.create = AsyncMock(return_value=mock_fw)
    mock_audit.async_log_change = AsyncMock()

    with patch("os.path.relpath", return_value="rel/path"):
        result = await firmware_service.upload_firmware(async_db_mock, "v1.0.0", mock_upload_file, 1)

    assert result == mock_fw
    mock_repo.create.assert_called_once()
    mock_audit.async_log_change.assert_called_once()
    mock_copy.assert_called_once_with(mock_upload_file.file, mock_file())


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
@patch("app.features.devices.firmware_service.async_firmware_repository")
@patch("app.features.devices.firmware_service.time.time", return_value=1234567890)
@patch("builtins.open", new_callable=mock_open)
@patch("shutil.copyfileobj")
async def test_upload_firmware_latest_invalid_version(mock_copy, mock_file, mock_time, mock_repo, firmware_service,
                                                      async_db_mock, mock_upload_file):
    latest_fw = Firmware(id=1, version="invalid")
    mock_repo.get_latest = AsyncMock(return_value=latest_fw)
    mock_repo.get_by_version = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock(return_value=Firmware(id=2, version="v1.0.0", file_path="path"))

    with patch("os.path.relpath", return_value="path"), patch(
            "app.features.devices.firmware_service.audit_service.async_log_change", new_callable=AsyncMock):
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
@patch("app.features.devices.firmware_service.async_firmware_repository")
@patch("app.features.devices.firmware_service.audit_service")
@patch("app.features.devices.firmware_service.time.time", return_value=1234567890)
@patch("builtins.open", new_callable=mock_open)
@patch("shutil.copyfileobj")
async def test_update_firmware_file_success(mock_copy, mock_file, mock_time, mock_audit, mock_repo, firmware_service,
                                            async_db_mock, mock_upload_file):
    old_fw = Firmware(id=1, version="v1.0.0", file_path="old/path")
    mock_repo.get_by_version = AsyncMock(return_value=old_fw)
    new_fw = Firmware(id=2, version="v1.0.0", file_path="new/path")
    mock_repo.create = AsyncMock(return_value=new_fw)
    mock_audit.async_log_change = AsyncMock()

    with patch("os.path.relpath", return_value="new/path"):
        result = await firmware_service.update_firmware_file(async_db_mock, "v1.0.0", mock_upload_file, 1)

    assert result == new_fw
    mock_repo.create.assert_called_once()
    mock_audit.async_log_change.assert_called_once()
    mock_copy.assert_called_once_with(mock_upload_file.file, mock_file())


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
@patch("app.features.devices.firmware_service.async_firmware_repository")
@patch("os.path.exists", return_value=True)
async def test_get_firmware_file_success_rel(mock_exists, mock_repo, firmware_service, async_db_mock):
    mock_repo.get_by_version = AsyncMock(return_value=Firmware(id=1, version="v1.0.0", file_path="rel/path"))
    with patch("os.path.isabs", return_value=False):
        with patch("os.path.join", return_value="/root/rel/path"):
            result = await firmware_service.get_firmware_file(async_db_mock, "v1.0.0")
    assert result == "/root/rel/path"


@pytest.mark.asyncio
@patch("app.features.devices.firmware_service.async_firmware_repository")
@patch("os.path.exists", return_value=True)
async def test_get_firmware_file_success_abs(mock_exists, mock_repo, firmware_service, async_db_mock):
    mock_repo.get_by_version = AsyncMock(return_value=Firmware(id=1, version="v1.0.0", file_path="/abs/path"))
    with patch("os.path.isabs", return_value=True):
        result = await firmware_service.get_firmware_file(async_db_mock, "v1.0.0")
    assert result == "/abs/path"


def test_firmware_service_repo_property(firmware_service):
    custom_repo = MagicMock()
    original_repo = firmware_service.repo
    try:
        firmware_service.repo = custom_repo
        assert firmware_service.repo == custom_repo
    finally:
        firmware_service.repo = original_repo
