from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.exc import SQLAlchemyError

import pytest
from app.features.devices.device_models import UserBiometric
from app.features.devices.punch_service import punch_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User


def _setup_scalars_mock(async_db_mock, return_value=None, side_effect=None):
    if side_effect:
        async_db_mock.scalars.side_effect = side_effect
    else:
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = return_value
        async_db_mock.scalars.return_value = scalars_mock


@pytest.mark.asyncio
async def test_process_biometric_punch_not_found(async_db_mock):
    _setup_scalars_mock(async_db_mock, return_value=None)
    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1)
    assert not success
    assert msg == "Nao Cadastrado"


@pytest.mark.asyncio
async def test_process_biometric_punch_blocked(async_db_mock):
    bio = UserBiometric(id=1, user=User(id=1, is_active=False))
    _setup_scalars_mock(async_db_mock, return_value=bio)
    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1)
    assert not success
    assert msg == "Bloqueado"


@pytest.mark.asyncio
async def test_process_biometric_punch_success_ntp(async_db_mock, mocker):
    bio = UserBiometric(id=1, user=User(id=1, is_active=True))
    record = TimeRecord(id=1)

    bio_scalars = MagicMock()
    bio_scalars.first.return_value = bio
    record_scalars = MagicMock()
    record_scalars.first.return_value = record
    async_db_mock.scalars.side_effect = [bio_scalars, record_scalars]

    mocker.patch(
        "app.features.devices.punch_service.trusted_time_service.get_trusted_time",
        return_value=(datetime(2023, 10, 1), True),
    )
    mocker.patch(
        "app.features.time_records.time_record_service.time_record_service.create_punch",
        return_value=record,
    )

    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1, "127.0.0.1")
    assert success
    assert msg == "Ponto Registrado"
    assert rec.id == 1


@pytest.mark.asyncio
async def test_process_biometric_punch_success_no_ntp_with_request(async_db_mock, mocker):
    bio = UserBiometric(id=1, user=User(id=1, is_active=True))
    record = TimeRecord(id=1)

    bio_scalars = MagicMock()
    bio_scalars.first.return_value = bio
    record_scalars = MagicMock()
    record_scalars.first.return_value = record
    async_db_mock.scalars.side_effect = [bio_scalars, record_scalars]

    mocker.patch(
        "app.features.devices.punch_service.trusted_time_service.get_trusted_time",
        return_value=(datetime(2023, 10, 1), False),
    )
    mocker.patch(
        "app.features.time_records.time_record_service.time_record_service.create_punch",
        return_value=record,
    )
    mocker.patch(
        "app.features.system.audit_service.audit_service.async_log_change",
        new_callable=AsyncMock,
    )

    req = MagicMock()
    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1, request=req)

    assert success
    assert req.state.ntp_error is True
    assert record.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."
    assert rec.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."


@pytest.mark.asyncio
async def test_process_biometric_punch_success_no_ntp_no_request(async_db_mock, mocker):
    bio = UserBiometric(id=1, user=User(id=1, is_active=True))
    record = TimeRecord(id=1)

    bio_scalars = MagicMock()
    bio_scalars.first.return_value = bio
    record_scalars = MagicMock()
    record_scalars.first.return_value = record
    async_db_mock.scalars.side_effect = [bio_scalars, record_scalars]

    mocker.patch(
        "app.features.devices.punch_service.trusted_time_service.get_trusted_time",
        return_value=(datetime(2023, 10, 1), False),
    )
    mocker.patch(
        "app.features.time_records.time_record_service.time_record_service.create_punch",
        return_value=record,
    )
    mocker.patch(
        "app.features.system.audit_service.audit_service.async_log_change",
        new_callable=AsyncMock,
    )

    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1)
    assert success
    assert record.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."
    assert rec.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."


@pytest.mark.asyncio
async def test_process_biometric_punch_sqlalchemy_exception(async_db_mock, mocker):
    _setup_scalars_mock(async_db_mock, side_effect=SQLAlchemyError("DB Error"))
    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1)
    assert not success
    assert msg == "Erro Interno"


@pytest.mark.asyncio
async def test_process_biometric_punch_value_error(async_db_mock, mocker):
    _setup_scalars_mock(async_db_mock, side_effect=ValueError("Value Error"))
    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1)
    assert not success
    assert msg == "Erro Interno"


@pytest.mark.asyncio
async def test_process_biometric_punch_refetch_returns_none(async_db_mock, mocker):
    bio = UserBiometric(id=1, user=User(id=1, is_active=True))
    record = TimeRecord(id=1)

    bio_scalars = MagicMock()
    bio_scalars.first.return_value = bio
    none_scalars = MagicMock()
    none_scalars.first.return_value = None
    async_db_mock.scalars.side_effect = [bio_scalars, none_scalars]

    mocker.patch(
        "app.features.devices.punch_service.trusted_time_service.get_trusted_time",
        return_value=(datetime(2023, 10, 1), True),
    )
    mocker.patch(
        "app.features.time_records.time_record_service.time_record_service.create_punch",
        return_value=record,
    )

    success, msg, rec = await punch_service.process_biometric_punch(async_db_mock, 1)
    assert success
    assert msg == "Ponto Registrado"
    assert rec is None


def test_punch_service_repo_property():
    mock_repo = MagicMock()
    punch_service.repo = mock_repo
    assert punch_service.repo == mock_repo
    punch_service.repo = None
    assert punch_service.repo is not None
