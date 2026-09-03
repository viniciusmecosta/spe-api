from unittest.mock import MagicMock, AsyncMock

import pytest


@pytest.fixture
def async_db_mock():
    from unittest.mock import MagicMock, AsyncMock
    session = MagicMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


from app.features.users.user_exceptions import (
    BiometricValidationError,
    InsufficientPrivilegesError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.features.devices.device_models import UserBiometric
from app.features.users.user_models import User
from app.features.users.user_schemas import UserUpdate
from app.features.users.user_service import UserService
from app.features.users.user_validator import UserValidator
from app.features.users.user_biometric_service import UserBiometricService
from app.shared.enums import UserRole


@pytest.fixture
def user_validator(async_db_mock):
    return UserValidator(db=async_db_mock)


@pytest.fixture
def biometric_service(async_db_mock):
    return UserBiometricService(db=async_db_mock)


@pytest.fixture
def user_service(async_db_mock, user_validator, biometric_service):
    service = UserService(db=async_db_mock, validator=user_validator, biometric_service=biometric_service)
    service.repository = MagicMock()
    return service


@pytest.mark.asyncio
async def test_get_multi(user_service):
    user_service.repository.get_multi = AsyncMock(return_value=["u1"])
    res = await user_service.get_multi(0, 10)
    assert res == ["u1"]


def test_get_user_me(user_service):
    mgr = User(id=1, role=UserRole.MANAGER, can_manual_punch_desktop=False, can_manual_punch_mobile=False)
    res_mgr = user_service.get_user_me(mgr)
    assert res_mgr["can_manual_punch_desktop"] is True
    assert res_mgr["can_manual_punch_mobile"] is True

    emp = User(id=2, role=UserRole.EMPLOYEE, can_manual_punch_desktop=True, can_manual_punch_mobile=False)
    res_emp = user_service.get_user_me(emp)
    assert res_emp["can_manual_punch_desktop"] is True
    assert res_emp["can_manual_punch_mobile"] is False


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(user_service):
    user_service.repository.get = AsyncMock(return_value=None)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    with pytest.raises(UserNotFoundError) as exc1:
        await user_service.get_user_by_id(999, current_mgr)
    assert exc1.value.status_code == 404


@pytest.mark.asyncio
async def test_get_user_by_id_forbidden_employee(user_service):
    target_user = User(id=2, role=UserRole.EMPLOYEE)
    user_service.repository.get = AsyncMock(return_value=target_user)
    current_emp = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(InsufficientPrivilegesError) as exc2:
        await user_service.get_user_by_id(2, current_emp)
    assert exc2.value.status_code == 403


@pytest.mark.asyncio
async def test_get_user_by_id_success(user_service):
    target_user = User(id=2, role=UserRole.EMPLOYEE)
    user_service.repository.get = AsyncMock(return_value=target_user)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    assert await user_service.get_user_by_id(2, current_mgr) == target_user


@pytest.mark.asyncio
async def test_update_user_by_admin_not_found(user_service):
    user_service.repository.get = AsyncMock(return_value=None)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    up = UserUpdate()
    with pytest.raises(UserNotFoundError) as exc1:
        await user_service.update_user_by_admin(999, up, current_mgr)
    assert exc1.value.status_code == 404


@pytest.mark.asyncio
async def test_update_user_by_admin_forbidden_maintainer(user_service):
    maint_user = User(id=2, role=UserRole.MAINTAINER)
    user_service.repository.get = AsyncMock(return_value=maint_user)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    up = UserUpdate()
    with pytest.raises(InsufficientPrivilegesError) as exc2:
        await user_service.update_user_by_admin(2, up, current_mgr)
    assert exc2.value.status_code == 403


@pytest.mark.asyncio
async def test_update_user_by_admin_success(user_service, mocker):
    emp_user = User(id=2, role=UserRole.EMPLOYEE)
    current_mgr = User(id=1, role=UserRole.MANAGER)
    up = UserUpdate()
    user_service.repository.get = AsyncMock(return_value=emp_user)
    mocker.patch.object(user_service, "update_user", new_callable=AsyncMock, return_value=emp_user)
    assert await user_service.update_user_by_admin(2, up, current_mgr) == emp_user


def test_get_bio_attr(biometric_service):
    assert biometric_service._get_bio_attr({"id": 1}, "id") == 1
    class Obj:
        id = 2

    assert biometric_service._get_bio_attr(Obj(), "id") == 2
    assert biometric_service._get_bio_attr(Obj(), "none") is None


@pytest.mark.asyncio
async def test_validate_sensor_index_none(biometric_service):
    user = User(id=1)
    seen = set()
    await biometric_service.validate_sensor_index(user, None, seen)
    assert len(seen) == 0


@pytest.mark.asyncio
async def test_validate_sensor_index_duplicate_request(biometric_service):
    user = User(id=1)
    seen = {1}
    with pytest.raises(BiometricValidationError) as exc:
        await biometric_service.validate_sensor_index(user, 1, seen)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_sensor_index_already_used_db(biometric_service, async_db_mock):
    user = User(id=1)
    seen = set()
    async_db_mock.scalar = AsyncMock(return_value=True)
    with pytest.raises(BiometricValidationError) as exc:
        await biometric_service.validate_sensor_index(user, 2, seen)
    assert exc.value.status_code == 400


def test_validate_finger_id_none(biometric_service):
    seen = set()
    biometric_service.validate_finger_id(None, seen)
    assert len(seen) == 0


def test_validate_finger_id_valid(biometric_service):
    seen = set()
    biometric_service.validate_finger_id(1, seen)
    assert 1 in seen


def test_validate_finger_id_duplicate(biometric_service):
    seen = {1}
    with pytest.raises(BiometricValidationError) as exc:
        biometric_service.validate_finger_id(1, seen)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_process_single_biometric(biometric_service, mocker):
    mocker.patch.object(biometric_service, "validate_sensor_index", new_callable=AsyncMock)
    mocker.patch.object(biometric_service, "validate_finger_id")
    user = User(id=1)
    seen_idx, seen_fgr = set(), set()
    existing = UserBiometric(id=10)
    current = {10: existing}
    res = await biometric_service.process_single_biometric(user,
                                                 {"id": 10, "sensor_index": 2, "template_data": "data", "finger_id": 3},
                                                 seen_idx, seen_fgr, current)
    assert res == existing
    assert res.sensor_index == 2
    assert res.template_data == "data"
    assert res.finger_id == 3
    res2 = await biometric_service.process_single_biometric(user,
                                                  {"id": 11, "sensor_index": 5, "template_data": "data2",
                                                   "finger_id": 4}, seen_idx, seen_fgr, current)
    assert res2.sensor_index == 5
    assert res2.template_data == "data2"
    assert res2.finger_id == 4


@pytest.mark.asyncio
async def test_validate_unique_fields_ok(user_validator, async_db_mock):
    async_db_mock.scalar = AsyncMock(return_value=False)
    await user_validator.validate_unique_fields(username="test", email="test@test.com", cpf="123")


@pytest.mark.asyncio
async def test_validate_unique_fields_dup_user(user_validator, async_db_mock):
    async_db_mock.scalar = AsyncMock(return_value=True)
    with pytest.raises(UserAlreadyExistsError) as exc:
        await user_validator.validate_unique_fields(username="test")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_unique_fields_dup_email(user_validator, async_db_mock):
    async_db_mock.scalar = AsyncMock(side_effect=[False, True])
    with pytest.raises(UserAlreadyExistsError) as exc:
        await user_validator.validate_unique_fields(username="test", email="test@test.com")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_unique_fields_dup_cpf(user_validator, async_db_mock):
    async_db_mock.scalar = AsyncMock(side_effect=[False, False, True])
    with pytest.raises(UserAlreadyExistsError) as exc:
        await user_validator.validate_unique_fields(username="test", email="test@test.com", cpf="123")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_user(user_service, mocker):
    mocker.patch.object(user_service.validator, "validate_unique_fields", new_callable=AsyncMock)
    user_service.repository.create = AsyncMock(return_value=User(name="Test", password_hash="hash"))
    mocker.patch("app.features.users.user_service.audit_service.async_log_change", new_callable=AsyncMock)

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

    user = await user_service.create_user(user_in, 99)
    assert user.name == "Test"
    assert user.password_hash == "hash"


@pytest.mark.asyncio
async def test_update_user_not_found(user_service):
    user_service.repository.get = AsyncMock(return_value=None)
    user_in = MagicMock()
    with pytest.raises(UserNotFoundError) as exc:
        await user_service.update_user(1, user_in, 99)
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


@pytest.mark.asyncio
async def test_update_user_ok(user_service, mocker):
    user = User(id=1, name="New", is_active=True, password_hash="hash")
    user_service.repository.get = AsyncMock(return_value=user)
    user_service.repository.update = AsyncMock(return_value=user)
    mocker.patch.object(user_service.validator, "validate_unique_fields", new_callable=AsyncMock)
    mock_log = mocker.patch("app.features.users.user_service.audit_service.async_log_change", new_callable=AsyncMock)

    user_in = UserUpdate(name="New", password="123456")
    user_in.biometrics = []

    res = await user_service.update_user(1, user_in, 99)
    assert res.name == "New"
    assert res.password_hash == "hash"
    mock_log.assert_called_once()
    assert mock_log.call_args[1]["new_data"] == {"password_changed": True}


def test_format_name(user_service):
    assert user_service._format_name("vinicius da costa") == "Vinicius da Costa"
    assert user_service._format_name("ze do carmo") == "Ze do Carmo"
    assert user_service._format_name("MARIA DAS GRACAS") == "Maria das Gracas"
    assert user_service._format_name("ana de almeida") == "Ana de Almeida"
    assert user_service._format_name("") == ""
    assert user_service._format_name("   ") == "   "
    assert user_service._format_name(None) is None


def test_extract_data_dict(user_service):
    res = user_service._extract_data({"key": "val"})
    assert res == {"key": "val"}
