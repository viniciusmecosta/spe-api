import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.services.user_service import user_service
from app.domain.models.user import User
from app.domain.models.biometric import UserBiometric
from app.schemas.user import UserCreate, UserUpdate
from app.domain.models.enums import UserRole

def test_get_bio_attr():
    assert user_service._get_bio_attr({"id": 1}, "id") == 1
    
    class Obj:
        id = 2
    assert user_service._get_bio_attr(Obj(), "id") == 2
    assert user_service._get_bio_attr(Obj(), "none") is None

def test_validate_sensor_index(db_session_mock):
    user = User(id=1)
    seen = set()
    user_service._validate_sensor_index(db_session_mock, user, None, seen)
    
    user_service._validate_sensor_index(db_session_mock, user, 1, seen)
    assert 1 in seen
    
    with pytest.raises(HTTPException) as exc:
        user_service._validate_sensor_index(db_session_mock, user, 1, seen)
    assert exc.value.status_code == 400

    db_session_mock.query.return_value.first = MagicMock(return_value=True)
    with pytest.raises(HTTPException) as exc:
        user_service._validate_sensor_index(db_session_mock, user, 2, set())
    assert exc.value.status_code == 400

def test_validate_finger_id():
    seen = set()
    user_service._validate_finger_id(None, seen)
    user_service._validate_finger_id(1, seen)
    assert 1 in seen
    with pytest.raises(HTTPException) as exc:
        user_service._validate_finger_id(1, seen)
    assert exc.value.status_code == 400

def test_process_single_biometric(db_session_mock, mocker):
    mocker.patch("app.services.user_service.UserService._validate_sensor_index")
    mocker.patch("app.services.user_service.UserService._validate_finger_id")
    
    user = User(id=1)
    seen_idx, seen_fgr = set(), set()
    
    existing = UserBiometric(id=10)
    current = {10: existing}
    
    res = user_service._process_single_biometric(db_session_mock, user, {"id": 10, "sensor_index": 2, "template_data": "data", "finger_id": 3}, seen_idx, seen_fgr, current)
    assert res == existing
    assert res.sensor_index == 2
    assert res.template_data == "data"
    assert res.finger_id == 3

    res2 = user_service._process_single_biometric(db_session_mock, user, {"id": 11, "sensor_index": 5, "template_data": "data2", "finger_id": 4}, seen_idx, seen_fgr, current)
    assert res2.sensor_index == 5
    assert res2.template_data == "data2"
    assert res2.finger_id == 4

def test_sync_biometrics(db_session_mock, mocker):
    mocker.patch("app.services.user_service.UserService._process_single_biometric", return_value=UserBiometric(id=1))
    user = User(id=1, biometrics=[])
    user_service._sync_biometrics(db_session_mock, user, [{"id": 1}])
    assert len(user.biometrics) == 1

def test_validate_unique_fields_ok(db_session_mock, mocker):
    mocker.patch("app.repositories.user_repository.user_repository.get_by_username", return_value=None)
    db_session_mock.query.return_value.first = MagicMock(return_value=None)
    user_in = MagicMock()
    user_in.username = "test"
    user_in.email = "test@test.com"
    user_in.cpf = "123"
    user_service._validate_unique_fields(db_session_mock, user_in)

def test_validate_unique_fields_dup_user(db_session_mock, mocker):
    mocker.patch("app.repositories.user_repository.user_repository.get_by_username", return_value=True)
    user_in = MagicMock()
    user_in.username = "test"
    with pytest.raises(HTTPException) as exc:
        user_service._validate_unique_fields(db_session_mock, user_in)
    assert exc.value.status_code == 400

def test_validate_unique_fields_dup_email(db_session_mock, mocker):
    mocker.patch("app.repositories.user_repository.user_repository.get_by_username", return_value=None)
    db_session_mock.query.return_value.first = MagicMock(return_value=True)
    user_in = MagicMock()
    user_in.username = "test"
    user_in.email = "test@test.com"
    with pytest.raises(HTTPException) as exc:
        user_service._validate_unique_fields(db_session_mock, user_in)
    assert exc.value.status_code == 400

def test_validate_unique_fields_dup_cpf(db_session_mock, mocker):
    mocker.patch("app.repositories.user_repository.user_repository.get_by_username", return_value=None)
    db_session_mock.query.return_value.first = MagicMock(side_effect=[None, True])
    user_in = MagicMock()
    user_in.username = "test"
    user_in.email = "test@test.com"
    user_in.cpf = "123"
    with pytest.raises(HTTPException) as exc:
        user_service._validate_unique_fields(db_session_mock, user_in)
    assert exc.value.status_code == 400

def test_create_user(db_session_mock, mocker):
    mocker.patch("app.services.user_service.UserService._validate_unique_fields")
    mocker.patch("app.services.user_service.get_password_hash", return_value="hash")
    mocker.patch("app.services.user_service.UserService._sync_biometrics")
    mocker.patch("app.services.audit_service.audit_service.log")

    class DummyCreate:
        pass
    user_in = DummyCreate()
    user_in.name = "Test"
    user_in.username = "test"
    user_in.password = "123456"
    user_in.email = "t@t.com"
    user_in.cpf = "12345678909"
    user_in.pis = "12345678909"
    user_in.role = UserRole.EMPLOYEE
    user_in.endereco = None
    user_in.data_nascimento = None
    user_in.is_active = True
    user_in.can_manual_punch_desktop = True
    user_in.can_manual_punch_mobile = False
    user_in.can_export_report = False
    user_in.biometrics = [{"id": 1}]

    user = user_service.create_user(db_session_mock, user_in, 99)
    assert user.name == "Test"
    assert user.password_hash == "hash"

def test_update_user_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.user_repository.user_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        user_service.update_user(db_session_mock, 1, MagicMock(), 99)
    assert exc.value.status_code == 404

def test_update_user_ok(db_session_mock, mocker):
    user = User(id=1, name="Old", is_active=True)
    mocker.patch("app.repositories.user_repository.user_repository.get", return_value=user)
    mocker.patch("app.services.user_service.UserService._validate_unique_fields")
    mocker.patch("app.services.user_service.get_password_hash", return_value="hash")
    mocker.patch("app.services.user_service.UserService._sync_biometrics")
    mocker.patch("app.services.audit_service.audit_service.compute_diffs", return_value=({"old":"val"}, {"new":"val"}))
    mocker.patch("app.services.audit_service.audit_service.log")

    user_in = UserUpdate(name="New", password="123456")
    user_in.biometrics = []

    res = user_service.update_user(db_session_mock, 1, user_in, 99)
    assert res.name == "New"
    assert res.password_hash == "hash"

def test_disable_user_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.user_repository.user_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        user_service.disable_user(db_session_mock, 1, 99)
    assert exc.value.status_code == 404

def test_disable_user_ok(db_session_mock, mocker):
    user = User(id=1, is_active=True)
    mocker.patch("app.repositories.user_repository.user_repository.get", return_value=user)
    mocker.patch("app.services.audit_service.audit_service.log")

    res = user_service.disable_user(db_session_mock, 1, 99)
    assert res.is_active is False
