import pytest
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from unittest.mock import MagicMock

from app.domain.models.biometric import UserBiometric
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User
from app.services.punch_service import punch_service


def _setup_query_mock(db_session_mock, return_value=None, side_effect=None):
    query_mock = MagicMock()
    if side_effect:
        query_mock.filter.side_effect = side_effect
    else:
        query_mock.filter.return_value.first.return_value = return_value
    db_session_mock.query = MagicMock(return_value=query_mock)

def test_process_biometric_punch_not_found(db_session_mock):
    _setup_query_mock(db_session_mock, return_value=None)
    success, msg, rec = punch_service.process_biometric_punch(db_session_mock, 1)
    assert not success
    assert msg == "Nao Cadastrado"

def test_process_biometric_punch_blocked(db_session_mock):
    bio = UserBiometric(id=1, user=User(id=1, is_active=False))
    _setup_query_mock(db_session_mock, return_value=bio)
    success, msg, rec = punch_service.process_biometric_punch(db_session_mock, 1)
    assert not success
    assert msg == "Bloqueado"

def test_process_biometric_punch_success_ntp(db_session_mock, mocker):
    bio = UserBiometric(id=1, user=User(id=1, is_active=True))
    _setup_query_mock(db_session_mock, return_value=bio)
    mocker.patch("app.services.punch_service.trusted_time_service.get_trusted_time",
                 return_value=(datetime(2023, 10, 1), True))
    mocker.patch("app.services.time_record_service.time_record_service.create_punch", return_value=TimeRecord(id=1))
    
    success, msg, rec = punch_service.process_biometric_punch(db_session_mock, 1, "127.0.0.1")
    assert success
    assert msg == "Ponto Registrado"
    assert rec.id == 1

def test_process_biometric_punch_success_no_ntp_with_request(db_session_mock, mocker):
    bio = UserBiometric(id=1, user=User(id=1, is_active=True))
    _setup_query_mock(db_session_mock, return_value=bio)
    mocker.patch("app.services.punch_service.trusted_time_service.get_trusted_time",
                 return_value=(datetime(2023, 10, 1), False))
    mocker.patch("app.services.time_record_service.time_record_service.create_punch", return_value=TimeRecord(id=1))
    mocker.patch("app.services.audit_service.audit_service.log")
    
    req = MagicMock()
    success, msg, rec = punch_service.process_biometric_punch(db_session_mock, 1, request=req)
    assert success
    assert req.state.ntp_error is True
    assert rec.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."

def test_process_biometric_punch_success_no_ntp_no_request(db_session_mock, mocker):
    bio = UserBiometric(id=1, user=User(id=1, is_active=True))
    _setup_query_mock(db_session_mock, return_value=bio)
    mocker.patch("app.services.punch_service.trusted_time_service.get_trusted_time",
                 return_value=(datetime(2023, 10, 1), False))
    mocker.patch("app.services.time_record_service.time_record_service.create_punch", return_value=TimeRecord(id=1))
    mocker.patch("app.services.audit_service.audit_service.log")
    
    success, msg, rec = punch_service.process_biometric_punch(db_session_mock, 1)
    assert success
    assert rec.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."

def test_process_biometric_punch_sqlalchemy_exception(db_session_mock, mocker):
    _setup_query_mock(db_session_mock, side_effect=SQLAlchemyError("DB Error"))
    success, msg, rec = punch_service.process_biometric_punch(db_session_mock, 1)
    assert not success
    assert msg == "Erro Interno"

def test_process_biometric_punch_value_error(db_session_mock, mocker):
    _setup_query_mock(db_session_mock, side_effect=ValueError("Value Error"))
    success, msg, rec = punch_service.process_biometric_punch(db_session_mock, 1)
    assert not success
    assert msg == "Erro Interno"
