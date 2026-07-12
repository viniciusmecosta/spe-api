import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError
from app.domain.models.biometric import UserBiometric
from app.domain.models.user import User
from app.services.biometric_service import biometric_service

def test_get_all_for_sync(db_session_mock):
    db_session_mock.query.return_value.join = MagicMock(return_value=db_session_mock.query.return_value)
    bio1 = UserBiometric(id=1, user_id=1, template_data="test1")
    bio2 = UserBiometric(id=2, user_id=2, template_data="test2")
    db_session_mock.query.return_value.items = [bio1, bio2]
    result = biometric_service.get_all_for_sync(db_session_mock)
    assert len(result) == 2
    assert result[0].biometric_id == 1
    assert result[0].template_data == "test1"
    assert result[0].user_id == 1
    assert result[1].biometric_id == 2
    assert result[1].template_data == "test2"
    assert result[1].user_id == 2

def test_process_sync_ack(db_session_mock):
    payload = MagicMock()
    with pytest.raises(NotImplementedError):
        biometric_service.process_sync_ack(db_session_mock, payload)

@patch("app.services.biometric_service.audit_service")
def test_save_enrolled_biometric_success(audit_mock, db_session_mock):
    payload = MagicMock()
    payload.success = True
    payload.user_id = 1
    payload.finger_id = 1
    payload.template_data = "data"
    payload.sensor_index = 1
    user = User(id=1)
    def side_effect(*args, **kwargs):
        if User in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = user
            return mock_query
        if UserBiometric in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = None
            return mock_query
        return MagicMock()
    db_session_mock.query.side_effect = side_effect
    success, msg = biometric_service.save_enrolled_biometric(db_session_mock, payload)
    assert success is True
    assert msg == "Sucesso"
    db_session_mock.add.assert_called_once()
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once()
    audit_mock.log.assert_called_once()

def test_save_enrolled_biometric_unsuccessful(db_session_mock):
    payload = MagicMock()
    payload.success = False
    payload.error = "Error message"
    success, msg = biometric_service.save_enrolled_biometric(db_session_mock, payload)
    assert success is False
    assert msg == "Error message"
    db_session_mock.add.assert_not_called()

def test_save_enrolled_biometric_user_not_found(db_session_mock):
    payload = MagicMock()
    payload.success = True
    payload.user_id = 1
    payload.finger_id = 1
    payload.template_data = "data"
    payload.sensor_index = 1
    def side_effect(*args, **kwargs):
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        return mock_query
    db_session_mock.query.side_effect = side_effect
    success, msg = biometric_service.save_enrolled_biometric(db_session_mock, payload)
    assert success is False
    assert msg == "Usuario nao encontrado"

def test_save_enrolled_biometric_finger_already_exists(db_session_mock):
    payload = MagicMock()
    payload.success = True
    payload.user_id = 1
    payload.finger_id = 1
    payload.template_data = "data"
    payload.sensor_index = 1
    user = User(id=1)
    existing_finger = UserBiometric(id=1)
    def side_effect(*args, **kwargs):
        if User in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = user
            return mock_query
        if UserBiometric in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = existing_finger
            return mock_query
        return MagicMock()
    db_session_mock.query.side_effect = side_effect
    success, msg = biometric_service.save_enrolled_biometric(db_session_mock, payload)
    assert success is False
    assert msg == "O usuario ja possui uma biometria cadastrada para o dedo com ID 1"

def test_save_enrolled_biometric_sqlalchemy_error(db_session_mock):
    payload = MagicMock()
    payload.success = True
    payload.user_id = 1
    payload.finger_id = 1
    payload.template_data = "data"
    payload.sensor_index = 1
    user = User(id=1)
    def side_effect(*args, **kwargs):
        if User in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = user
            return mock_query
        if UserBiometric in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = None
            return mock_query
        return MagicMock()
    db_session_mock.query.side_effect = side_effect
    db_session_mock.add.side_effect = SQLAlchemyError("DB Error")
    success, msg = biometric_service.save_enrolled_biometric(db_session_mock, payload)
    assert success is False
    assert msg == "DB Error"

def test_save_enrolled_biometric_value_error(db_session_mock):
    payload = MagicMock()
    payload.success = True
    payload.user_id = 1
    payload.finger_id = 1
    payload.template_data = "data"
    payload.sensor_index = 1
    user = User(id=1)
    def side_effect(*args, **kwargs):
        if User in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = user
            return mock_query
        if UserBiometric in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = None
            return mock_query
        return MagicMock()
    db_session_mock.query.side_effect = side_effect
    db_session_mock.add.side_effect = ValueError("Value Error")
    success, msg = biometric_service.save_enrolled_biometric(db_session_mock, payload)
    assert success is False
    assert msg == "Value Error"

@patch("app.services.biometric_service.audit_service")
def test_save_enrolled_biometric_finger_id_none(audit_mock, db_session_mock):
    payload = MagicMock()
    payload.success = True
    payload.user_id = 1
    payload.finger_id = None
    payload.template_data = "data"
    payload.sensor_index = 1
    user = User(id=1)
    def side_effect(*args, **kwargs):
        if User in args:
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = user
            return mock_query
        return MagicMock()
    db_session_mock.query.side_effect = side_effect
    success, msg = biometric_service.save_enrolled_biometric(db_session_mock, payload)
    assert success is True
    assert msg == "Sucesso"
    audit_mock.log.assert_called_once()

def test_get_available_sensor_indices(db_session_mock):
    db_session_mock.query.return_value.items = [(1,), (3,), (5,)]
    result = biometric_service.get_available_sensor_indices(db_session_mock)
    expected = set(range(1, 128)) - {1, 3, 5}
    assert result == sorted(list(expected))

def test_get_available_sensor_indices_empty(db_session_mock):
    db_session_mock.query.return_value.items = []
    result = biometric_service.get_available_sensor_indices(db_session_mock)
    expected = set(range(1, 128))
    assert result == sorted(list(expected))
