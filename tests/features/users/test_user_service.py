from unittest.mock import MagicMock

import pytest
from app.features.users.user_exceptions import (
    BiometricValidationError,
    InsufficientPrivilegesError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.features.devices.device_models import UserBiometric
from app.features.users.user_models import User
from app.features.users.user_schemas import UserUpdate
from app.features.users.user_service import user_service
from app.shared.enums import UserRole


def test_get_multi(db_session_mock, mocker):
    mocker.patch("app.features.users.user_repository.user_repository.get_multi", return_value=["u1"])
    res = user_service.get_multi(db_session_mock, 0, 10)
    assert res == ["u1"]


def test_get_user_me():
    mgr = User(id=1, role=UserRole.MANAGER, can_manual_punch_desktop=False, can_manual_punch_mobile=False)
    res_mgr = user_service.get_user_me(mgr)
    assert res_mgr["can_manual_punch_desktop"] is True
    assert res_mgr["can_manual_punch_mobile"] is True

    emp = User(id=2, role=UserRole.EMPLOYEE, can_manual_punch_desktop=True, can_manual_punch_mobile=False)
    res_emp = user_service.get_user_me(emp)
    assert res_emp["can_manual_punch_desktop"] is True
    assert res_emp["can_manual_punch_mobile"] is False


def test_get_user_by_id_not_found(db_session_mock, mocker):
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=None)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    with pytest.raises(UserNotFoundError) as exc1:
        user_service.get_user_by_id(db_session_mock, 999, current_mgr)
    assert exc1.value.status_code == 404


def test_get_user_by_id_forbidden_employee(db_session_mock, mocker):
    target_user = User(id=2, role=UserRole.EMPLOYEE)
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=target_user)
    current_emp = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(InsufficientPrivilegesError) as exc2:
        user_service.get_user_by_id(db_session_mock, 2, current_emp)
    assert exc2.value.status_code == 403


def test_get_user_by_id_success(db_session_mock, mocker):
    target_user = User(id=2, role=UserRole.EMPLOYEE)
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=target_user)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    assert user_service.get_user_by_id(db_session_mock, 2, current_mgr) == target_user


def test_update_user_by_admin_not_found(db_session_mock, mocker):
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=None)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    up = UserUpdate()
    with pytest.raises(UserNotFoundError) as exc1:
        user_service.update_user_by_admin(db_session_mock, 999, up, current_mgr)
    assert exc1.value.status_code == 404


def test_update_user_by_admin_forbidden_maintainer(db_session_mock, mocker):
    maint_user = User(id=2, role=UserRole.MAINTAINER)
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=maint_user)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    up = UserUpdate()
    with pytest.raises(InsufficientPrivilegesError) as exc2:
        user_service.update_user_by_admin(db_session_mock, 2, up, current_mgr)
    assert exc2.value.status_code == 403


def test_update_user_by_admin_success(db_session_mock, mocker):
    emp_user = User(id=2, role=UserRole.EMPLOYEE)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    up = UserUpdate()
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=emp_user)
    mocker.patch("app.features.users.user_service.user_service.update_user", return_value=emp_user)
    assert user_service.update_user_by_admin(db_session_mock, 2, up, current_mgr) == emp_user


def test_get_bio_attr():
    assert user_service._get_bio_attr({"id": 1}, "id") == 1

    class Obj:
        id = 2

    assert user_service._get_bio_attr(Obj(), "id") == 2
    assert user_service._get_bio_attr(Obj(), "none") is None


def test_validate_sensor_index_none(db_session_mock):
    user = User(id=1)
    seen = set()
    user_service._validate_sensor_index(db_session_mock, user, None, seen)
    assert len(seen) == 0


def test_validate_sensor_index_duplicate_request(db_session_mock):
    user = User(id=1)
    seen = {1}
    with pytest.raises(BiometricValidationError) as exc:
        user_service._validate_sensor_index(db_session_mock, user, 1, seen)
    assert exc.value.status_code == 400


def test_validate_sensor_index_already_used_db(db_session_mock):
    user = User(id=1)
    seen = set()
    db_session_mock.query.return_value.scalar = MagicMock(return_value=True)
    with pytest.raises(BiometricValidationError) as exc:
        user_service._validate_sensor_index(db_session_mock, user, 2, seen)
    assert exc.value.status_code == 400


def test_validate_finger_id_none():
    seen = set()
    user_service._validate_finger_id(None, seen)
    assert len(seen) == 0


def test_validate_finger_id_valid():
    seen = set()
    user_service._validate_finger_id(1, seen)
    assert 1 in seen


def test_validate_finger_id_duplicate():
    seen = {1}
    with pytest.raises(BiometricValidationError) as exc:
        user_service._validate_finger_id(1, seen)
    assert exc.value.status_code == 400


def test_process_single_biometric(db_session_mock, mocker):
    mocker.patch("app.features.users.user_service.UserService._validate_sensor_index")
    mocker.patch("app.features.users.user_service.UserService._validate_finger_id")

    user = User(id=1)
    seen_idx, seen_fgr = set(), set()

    existing = UserBiometric(id=10)
    current = {10: existing}

    res = user_service._process_single_biometric(db_session_mock, user,
                                                 {"id": 10, "sensor_index": 2, "template_data": "data", "finger_id": 3},
                                                 seen_idx, seen_fgr, current)
    assert res == existing
    assert res.sensor_index == 2
    assert res.template_data == "data"
    assert res.finger_id == 3

    res2 = user_service._process_single_biometric(db_session_mock, user,
                                                  {"id": 11, "sensor_index": 5, "template_data": "data2",
                                                   "finger_id": 4}, seen_idx, seen_fgr, current)
    assert res2.sensor_index == 5
    assert res2.template_data == "data2"
    assert res2.finger_id == 4


def test_sync_biometrics(db_session_mock, mocker):
    mocker.patch("app.features.users.user_service.UserService._process_single_biometric",
                 return_value=UserBiometric(id=1))
    user = User(id=1, biometrics=[])
    user_service._sync_biometrics(db_session_mock, user, [{"id": 1}])
    assert len(user.biometrics) == 1


def test_validate_unique_fields_ok(db_session_mock):
    db_session_mock.query.return_value.scalar = MagicMock(return_value=False)
    user_in = MagicMock()
    user_in.username = "test"
    user_in.email = "test@test.com"
    user_in.cpf = "123"
    user_service._validate_unique_fields(db_session_mock, user_in)


def test_validate_unique_fields_dup_user(db_session_mock):
    db_session_mock.query.return_value.scalar = MagicMock(return_value=True)
    user_in = MagicMock()
    user_in.username = "test"
    with pytest.raises(UserAlreadyExistsError) as exc:
        user_service._validate_unique_fields(db_session_mock, user_in)
    assert exc.value.status_code == 400


def test_validate_unique_fields_dup_email(db_session_mock):
    db_session_mock.query.return_value.scalar = MagicMock(side_effect=[False, True])
    user_in = MagicMock()
    user_in.username = "test"
    user_in.email = "test@test.com"
    with pytest.raises(UserAlreadyExistsError) as exc:
        user_service._validate_unique_fields(db_session_mock, user_in)
    assert exc.value.status_code == 400


def test_validate_unique_fields_dup_cpf(db_session_mock):
    db_session_mock.query.return_value.scalar = MagicMock(side_effect=[False, False, True])
    user_in = MagicMock()
    user_in.username = "test"
    user_in.email = "test@test.com"
    user_in.cpf = "123"
    with pytest.raises(UserAlreadyExistsError) as exc:
        user_service._validate_unique_fields(db_session_mock, user_in)
    assert exc.value.status_code == 400


def test_create_user(db_session_mock, mocker):
    mocker.patch("app.features.users.user_service.UserService._validate_unique_fields")
    mocker.patch("app.features.users.user_service.get_password_hash", return_value="hash")
    mocker.patch("app.features.users.user_service.UserService._sync_biometrics")
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

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
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=None)
    user_in = MagicMock()
    with pytest.raises(UserNotFoundError) as exc:
        user_service.update_user(db_session_mock, 1, user_in, 99)
    assert exc.value.status_code == 404


def test_serialize_user_state():
    from datetime import date
    from app.features.system.audit_service import serialize_model
    user = User(
        id=1, username="test", is_active=True, data_nascimento=date(2000, 1, 1),
        is_exempt_from_rules=False, is_tolerance_exempt=True
    )
    state = serialize_model(user)
    assert state["is_active"] is True
    assert state["data_nascimento"] == "2000-01-01"
    assert state["is_exempt_from_rules"] is False
    assert state["is_tolerance_exempt"] is True


def test_update_user_ok(db_session_mock, mocker):
    user = User(id=1, name="Old", is_active=True)
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=user)
    mocker.patch("app.features.users.user_service.UserService._validate_unique_fields")
    mocker.patch("app.features.users.user_service.get_password_hash", return_value="hash")
    mocker.patch("app.features.users.user_service.UserService._sync_biometrics")
    mock_log = mocker.patch("app.features.system.audit_service.audit_service.log_change")

    user_in = UserUpdate(name="New", password="123456")
    user_in.biometrics = []

    res = user_service.update_user(db_session_mock, 1, user_in, 99)
    assert res.name == "New"
    assert res.password_hash == "hash"
    mock_log.assert_called_once()
    assert mock_log.call_args[1]["new_data"] == {"password_changed": True}


def test_disable_user_not_found(db_session_mock, mocker):
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=None)
    with pytest.raises(UserNotFoundError) as exc:
        user_service.disable_user(db_session_mock, 1, 99)
    assert exc.value.status_code == 404


def test_disable_user_ok(db_session_mock, mocker):
    user = User(id=1, is_active=True)
    mocker.patch("app.features.users.user_repository.user_repository.get", return_value=user)
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    res = user_service.disable_user(db_session_mock, 1, 99)
    assert res.is_active is False


def test_format_name():
    assert user_service._format_name("vinicius da costa") == "Vinicius da Costa"
    assert user_service._format_name("ze do carmo") == "Ze do Carmo"
    assert user_service._format_name("MARIA DAS GRACAS") == "Maria das Gracas"
    assert user_service._format_name("ana de almeida") == "Ana de Almeida"
    assert user_service._format_name("") == ""
    assert user_service._format_name("   ") == "   "
    assert user_service._format_name(None) is None
