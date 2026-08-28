from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock

from app.features.holidays.holiday_models import Holiday
from app.features.system.audit_service import audit_service, serialize_model
from app.features.system.system_models import AuditLog
from app.features.system.system_repository import audit_repository
from app.features.system.system_schemas import AuditLogCreate
from app.features.users.user_models import User
from app.shared.enums import UserRole


def test_serialize_model_none():
    assert serialize_model(None) == {}
    assert serialize_model(12345) == {}


def test_serialize_regular_model():
    class CustomObj:
        def __init__(self):
            self.name = "Custom"
            self.value = 100
            self.password_hash = "secret"
            self._private = "ignore"

    obj = CustomObj()
    res = serialize_model(obj)
    assert res == {"name": "Custom", "value": 100}


def test_prepare_raw_data_with_both_model_and_data(db_session_mock, mocker):
    mock_create = mocker.patch("app.features.system.audit_service.audit_repository.create")
    holiday = Holiday(id=5, name="Natal", date=date(2026, 12, 25))
    audit_service.log_change(
        db_session_mock,
        user_id=2,
        action="UPDATE_HOLIDAY",
        new_model=holiday,
        new_data={"extra_field": "extra_val"}
    )
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[1].new_data["name"] == "Natal"
    assert args[1].new_data["extra_field"] == "extra_val"


def test_serialize_model_dict():
    raw_dict = {
        "date_val": date(2026, 1, 1),
        "dt_val": datetime(2026, 1, 1, 12, 0, 0),
        "time_val": time(8, 30, 0),
        "enum_val": UserRole.MANAGER,
        "dec_val": Decimal("42.50"),
        "str_val": "hello",
        "int_val": 100,
        "bool_val": True,
    }
    serialized = serialize_model(raw_dict)
    assert serialized == {
        "date_val": "2026-01-01",
        "dt_val": "2026-01-01T12:00:00",
        "time_val": "08:30:00",
        "enum_val": "MANAGER",
        "dec_val": 42.5,
        "str_val": "hello",
        "int_val": 100,
        "bool_val": True,
    }


def test_serialize_model_excludes_password_hash():
    user = User(id=1, username="test", password_hash="secret_hash", name="Test")
    res = serialize_model(user)
    assert "password_hash" not in res
    assert res["username"] == "test"
    assert res["name"] == "Test"


def test_serialize_model_column_types():
    class DummyCol:
        def __init__(self, name):
            self.name = name

    class DummyTable:
        columns = [
            DummyCol("dt_col"),
            DummyCol("date_col"),
            DummyCol("time_col"),
            DummyCol("enum_col"),
            DummyCol("dec_col"),
            DummyCol("bytes_col"),
            DummyCol("bytearray_col"),
            DummyCol("str_col"),
            DummyCol("password_hash"),
        ]

    class DummyModel:
        __table__ = DummyTable()
        dt_col = datetime(2026, 5, 1, 10, 0, 0)
        date_col = date(2026, 5, 1)
        time_col = time(10, 0, 0)
        enum_col = UserRole.MANAGER
        dec_col = Decimal("19.99")
        bytes_col = b"raw_data"
        bytearray_col = bytearray(b"byte_data")
        str_col = "sample"
        password_hash = "secret"

    res = serialize_model(DummyModel())
    assert res["dt_col"] == "2026-05-01T10:00:00"
    assert res["date_col"] == "2026-05-01"
    assert res["time_col"] == "10:00:00"
    assert res["enum_col"] == "MANAGER"
    assert res["dec_col"] == 19.99
    assert res["bytes_col"] == "<binary>"
    assert res["bytearray_col"] == "<binary>"
    assert res["str_col"] == "sample"
    assert "password_hash" not in res


def test_serialize_model_ignores_relationships():
    class DummyRel:
        def __init__(self, key):
            self.key = key

    class DummyMapper:
        def __init__(self, rels):
            self.relationships = rels

    rel_single = DummyRel("company")
    rel_list = DummyRel("holidays")

    class ParentModel:
        __table__ = MagicMock(columns=[])
        __mapper__ = DummyMapper([rel_single, rel_list])

        def __init__(self):
            self.company = Holiday(id=1, name="Parent Comp", date=date(2026, 1, 1))
            self.holidays = [
                Holiday(id=2, name="Holiday 1", date=date(2026, 1, 2)),
            ]

    parent = ParentModel()
    res = serialize_model(parent)
    assert "company" not in res
    assert "holidays" not in res


def test_log(db_session_mock, mocker):
    mock_create = mocker.patch("app.features.system.audit_service.audit_repository.create")
    mock_create.return_value = "mock_audit_log"
    result = audit_service.log(
        db_session_mock,
        42,
        "UPDATE",
        entity="User",
        entity_id=1,
        old_data={"name": "Old"},
        new_data={"name": "New"}
    )
    assert result == "mock_audit_log"
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[0] == db_session_mock
    assert isinstance(args[1], AuditLogCreate)
    assert args[1].action == "UPDATE"
    assert args[1].entity == "User"
    assert args[1].entity_id == 1
    assert args[1].user_id == 42
    assert args[1].old_data == {"name": "Old"}
    assert args[1].new_data == {"name": "New"}


def test_log_change_diff(db_session_mock, mocker):
    mock_create = mocker.patch("app.features.system.audit_service.audit_repository.create")
    mock_create.return_value = "created_log"

    old_user = User(id=1, username="old_user", name="Old User", role=UserRole.EMPLOYEE)
    new_user = User(id=1, username="old_user", name="New User", role=UserRole.MANAGER)

    res = audit_service.log_change(
        db_session_mock,
        user_id=10,
        action="UPDATE_USER",
        old_model=old_user,
        new_model=new_user
    )

    assert res == "created_log"
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[1].action == "UPDATE_USER"
    assert args[1].entity == "USERS"
    assert args[1].entity_id == 1
    assert args[1].user_id == 10
    assert args[1].old_data == {"name": "Old User", "role": "EMPLOYEE"}
    assert args[1].new_data == {"name": "New User", "role": "MANAGER"}


def test_log_change_create_only(db_session_mock, mocker):
    mock_create = mocker.patch("app.features.system.audit_service.audit_repository.create")
    holiday = Holiday(id=5, name="Natal", date=date(2026, 12, 25))
    audit_service.log_change(
        db_session_mock,
        user_id=2,
        action="CREATE_HOLIDAY",
        new_model=holiday
    )
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[1].action == "CREATE_HOLIDAY"
    assert args[1].entity == "HOLIDAYS"
    assert args[1].entity_id == 5
    assert args[1].old_data is None
    assert args[1].new_data["name"] == "Natal"
    assert args[1].new_data["date"] == "2026-12-25"


def test_log_change_delete_only(db_session_mock, mocker):
    mock_create = mocker.patch("app.features.system.audit_service.audit_repository.create")
    holiday = Holiday(id=5, name="Natal", date=date(2026, 12, 25))
    audit_service.log_change(
        db_session_mock,
        user_id=2,
        action="DELETE_HOLIDAY",
        old_model=holiday
    )
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[1].action == "DELETE_HOLIDAY"
    assert args[1].entity == "HOLIDAYS"
    assert args[1].entity_id == 5
    assert args[1].old_data["name"] == "Natal"
    assert args[1].new_data is None


def test_log_change_explicit_entity_and_id(db_session_mock, mocker):
    mock_create = mocker.patch("app.features.system.audit_service.audit_repository.create")
    holiday = Holiday(id=5, name="Natal", date=date(2026, 12, 25))
    audit_service.log_change(
        db_session_mock,
        user_id=2,
        action="CUSTOM_ACTION",
        entity="CUSTOM_ENTITY",
        entity_id=999,
        new_model=holiday
    )
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[1].action == "CUSTOM_ACTION"
    assert args[1].entity == "CUSTOM_ENTITY"
    assert args[1].entity_id == 999


def test_log_change_fallbacks(db_session_mock, mocker):
    mock_create = mocker.patch("app.features.system.audit_service.audit_repository.create")
    audit_service.log_change(
        db_session_mock,
        user_id=3,
        action="SYSTEM_EVENT",
        old_data={"status": "inactive"},
        new_data={"status": "active"}
    )
    mock_create.assert_called_once()
    args, _ = mock_create.call_args
    assert args[1].action == "SYSTEM_EVENT"
    assert args[1].entity == "SYSTEM"
    assert args[1].entity_id == 0
    assert args[1].old_data == {"status": "inactive"}
    assert args[1].new_data == {"status": "active"}


def test_compute_diffs():
    old_data = {"a": 1, "b": 2, "c": 3}
    new_data = {"a": 1, "b": 20, "d": 4}
    actual_old, actual_new = audit_service.compute_diffs(old_data, new_data)
    assert actual_old == {"b": 2, "c": 3}
    assert actual_new == {"b": 20, "d": 4}


def test_compute_diffs_identical():
    data = {"a": 1}
    actual_old, actual_new = audit_service.compute_diffs(data, data)
    assert actual_old == {}
    assert actual_new == {}


import pytest


@pytest.mark.asyncio
async def test_get_logs(db_session_mock, mocker):
    mock_get_logs = mocker.patch("app.features.system.audit_service.audit_repository.get_logs")
    mock_get_logs.return_value = ["log1", "log2"]
    start = date(2023, 1, 1)
    end = date(2023, 12, 31)
    result = await audit_service.get_logs(
        db=db_session_mock,
        action="CREATE",
        start_date=start,
        end_date=end,
        order_by="asc",
        skip=10,
        limit=50
    )
    assert result == ["log1", "log2"]
    mock_get_logs.assert_called_once_with(
        db_session_mock,
        action="CREATE",
        start_date=start,
        end_date=end,
        order_by="asc",
        skip=10,
        limit=50
    )


def test_audit_repository_create(db_session_mock):
    obj_in = AuditLogCreate(
        user_id=1,
        action="TEST_ACTION",
        entity="USER",
        entity_id=10,
        old_data={"name": "Old"},
        new_data={"name": "New"}
    )
    res = audit_repository.create(db_session_mock, obj_in)
    assert isinstance(res, AuditLog)
    assert res.user_id == 1
    assert res.action == "TEST_ACTION"
    assert res.entity == "USER"
    assert res.entity_id == 10
    assert res.old_data == {"name": "Old"}
    assert res.new_data == {"name": "New"}
    db_session_mock.add.assert_called_once()
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once()


def test_audit_repository_get_logs():
    db_mock = MagicMock()
    query_mock = MagicMock()
    db_mock.query.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = ["audit1", "audit2"]

    res_asc = audit_repository.get_logs(
        db_mock,
        action="LOGIN",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        order_by="asc",
        skip=5,
        limit=20
    )
    assert res_asc == ["audit1", "audit2"]

    res_desc = audit_repository.get_logs(
        db_mock,
        action=None,
        start_date=None,
        end_date=None,
        order_by="desc",
        skip=0,
        limit=100
    )
    assert res_desc == ["audit1", "audit2"]
