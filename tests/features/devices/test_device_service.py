from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.features.devices.device_schemas import FeedbackPayload, ManagerVerifyResponse, TimeResponsePayload
from app.features.devices.device_service import device_service
from app.shared.enums import RecordType, UserRole


@pytest.mark.asyncio
async def test_process_punch_success_entry(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_record = MagicMock()
    mock_record.user.name = "Vinicius Costa"
    mock_record.record_datetime = datetime(2026, 8, 14, 8, 30, 0)
    mock_record.record_type = RecordType.ENTRY

    mocker.patch(
        "app.features.devices.device_service.punch_service.process_biometric_punch",
        new_callable=AsyncMock,
        return_value=(True, "Sucesso", mock_record),
    )
    mocker.patch(
        "app.features.devices.device_service.time_record_service.trigger_auto_print"
    )

    request = MagicMock()
    request.state = MagicMock()
    bg_mock = MagicMock()

    result = await device_service.process_punch(
        db=async_db_mock,
        sensor_index=1,
        ip_address="192.168.1.100",
        request=request,
        background_tasks=bg_mock,
    )

    assert isinstance(result, FeedbackPayload)
    assert result.led == "green"
    assert "Vinicius" in result.line1
    assert result.line2 == "08:30"
    assert result.line3 == "Entrada"
    assert len(result.actions.buzzer_melody) == 3
    assert request.state.attempted_user == "Vinicius Costa"


@pytest.mark.asyncio
async def test_process_punch_success_exit_no_user_name(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_record = MagicMock()
    mock_record.user = None
    mock_record.record_datetime = datetime(2026, 8, 14, 17, 0, 0)
    mock_record.record_type = RecordType.EXIT

    mocker.patch(
        "app.features.devices.device_service.punch_service.process_biometric_punch",
        new_callable=AsyncMock,
        return_value=(True, "Sucesso", mock_record),
    )

    result = await device_service.process_punch(
        db=async_db_mock,
        sensor_index=2,
        ip_address="192.168.1.100",
        request=None,
    )

    assert isinstance(result, FeedbackPayload)
    assert result.led == "green"
    assert result.line1 == "Usuario"
    assert result.line2 == "17:00"
    assert result.line3 == "Saida"


@pytest.mark.asyncio
async def test_process_punch_failure(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_service.punch_service.process_biometric_punch",
        new_callable=AsyncMock,
        return_value=(False, "Biometria desconhecida", None),
    )

    result = await device_service.process_punch(
        db=async_db_mock,
        sensor_index=99,
        ip_address="192.168.1.100",
    )

    assert isinstance(result, FeedbackPayload)
    assert result.led == "red"
    assert result.line1 == "Erro"
    assert result.line2 == "Biometria descon"
    assert result.line3 == ""


@pytest.mark.asyncio
async def test_process_punch_failure_empty_message(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_service.punch_service.process_biometric_punch",
        new_callable=AsyncMock,
        return_value=(False, None, None),
    )

    result = await device_service.process_punch(
        db=async_db_mock,
        sensor_index=99,
        ip_address="192.168.1.100",
    )

    assert isinstance(result, FeedbackPayload)
    assert result.led == "red"
    assert result.line1 == "Erro"
    assert result.line2 == ""


@pytest.mark.asyncio
async def test_process_punch_exception(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_service.punch_service.process_biometric_punch",
        side_effect=Exception("Database crash"),
    )

    result = await device_service.process_punch(
        db=async_db_mock,
        sensor_index=1,
        ip_address="192.168.1.100",
    )

    assert isinstance(result, FeedbackPayload)
    assert result.led == "red"
    assert result.line1 == "Erro Interno"
    assert result.line2 == "Contate Admin"


def test_get_device_time(mocker: MagicMock) -> None:
    tz = ZoneInfo(settings.TIMEZONE)
    fixed_time = datetime(2026, 8, 14, 12, 0, 0, tzinfo=tz)

    mocker.patch(
        "app.features.devices.device_service.trusted_time_service.get_trusted_time",
        return_value=(fixed_time, True),
    )

    result = device_service.get_device_time()

    assert isinstance(result, TimeResponsePayload)
    assert result.unix == int(fixed_time.timestamp())
    assert result.formatted == "14/08/2026 12:00:00"


@pytest.mark.asyncio
async def test_verify_manager_access_no_managers(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_manager_with_biometric",
        new_callable=AsyncMock,
        return_value=None,
    )
    audit_mock = mocker.patch("app.features.devices.device_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_service.verify_manager_access(
        db=async_db_mock,
        sensor_index=1,
        device_id=10,
    )

    assert isinstance(result, ManagerVerifyResponse)
    assert result.is_allowed is True
    assert "Nenhum gestor cadastrado" in result.message
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_verify_manager_access_biometric_not_found(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_manager_with_biometric",
        new_callable=AsyncMock,
        return_value=MagicMock(),
    )
    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_by_sensor_index",
        new_callable=AsyncMock,
        return_value=None,
    )
    audit_mock = mocker.patch("app.features.devices.device_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_service.verify_manager_access(
        db=async_db_mock,
        sensor_index=99,
        device_id=10,
    )

    assert isinstance(result, ManagerVerifyResponse)
    assert result.is_allowed is False
    assert "Biometria não encontrada" in result.message
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_verify_manager_access_authorized_manager(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_bio = MagicMock()
    mock_bio.user.id = 5
    mock_bio.user.role = UserRole.MANAGER
    mock_bio.user.is_active = True

    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_manager_with_biometric",
        new_callable=AsyncMock,
        return_value=mock_bio,
    )
    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_by_sensor_index",
        new_callable=AsyncMock,
        return_value=mock_bio,
    )
    audit_mock = mocker.patch("app.features.devices.device_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_service.verify_manager_access(
        db=async_db_mock,
        sensor_index=5,
        device_id=10,
    )

    assert isinstance(result, ManagerVerifyResponse)
    assert result.is_allowed is True
    assert "Acesso autorizado" in result.message
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_verify_manager_access_authorized_maintainer(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_bio = MagicMock()
    mock_bio.user.id = 6
    mock_bio.user.role = UserRole.MAINTAINER
    mock_bio.user.is_active = True

    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_manager_with_biometric",
        new_callable=AsyncMock,
        return_value=mock_bio,
    )
    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_by_sensor_index",
        new_callable=AsyncMock,
        return_value=mock_bio,
    )
    audit_mock = mocker.patch("app.features.devices.device_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_service.verify_manager_access(
        db=async_db_mock,
        sensor_index=6,
        device_id=10,
    )

    assert isinstance(result, ManagerVerifyResponse)
    assert result.is_allowed is True
    assert "Acesso autorizado" in result.message
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_verify_manager_access_denied_role(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_bio = MagicMock()
    mock_bio.user.id = 7
    mock_bio.user.role = UserRole.EMPLOYEE
    mock_bio.user.is_active = True

    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_manager_with_biometric",
        new_callable=AsyncMock,
        return_value=MagicMock(),
    )
    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_by_sensor_index",
        new_callable=AsyncMock,
        return_value=mock_bio,
    )
    audit_mock = mocker.patch("app.features.devices.device_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_service.verify_manager_access(
        db=async_db_mock,
        sensor_index=7,
        device_id=10,
    )

    assert isinstance(result, ManagerVerifyResponse)
    assert result.is_allowed is False
    assert "Acesso negado" in result.message
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_verify_manager_access_denied_inactive(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_bio = MagicMock()
    mock_bio.user.id = 8
    mock_bio.user.role = UserRole.MANAGER
    mock_bio.user.is_active = False

    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_manager_with_biometric",
        new_callable=AsyncMock,
        return_value=MagicMock(),
    )
    mocker.patch(
        "app.features.devices.device_service.async_biometric_repository.get_by_sensor_index",
        new_callable=AsyncMock,
        return_value=mock_bio,
    )
    audit_mock = mocker.patch("app.features.devices.device_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await device_service.verify_manager_access(
        db=async_db_mock,
        sensor_index=8,
        device_id=10,
    )

    assert isinstance(result, ManagerVerifyResponse)
    assert result.is_allowed is False
    assert "Acesso negado" in result.message
    audit_mock.assert_called_once()
