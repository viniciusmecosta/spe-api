from datetime import date
from app.services.audit_service import audit_service
from app.schemas.audit import AuditLogCreate

def test_log(db_session_mock, mocker):
    mock_create = mocker.patch("app.services.audit_service.audit_repository.create")
    mock_create.return_value = "mock_audit_log"
    result = audit_service.log(
        db=db_session_mock,
        action="UPDATE",
        entity="User",
        entity_id=1,
        user_id=42,
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

def test_get_logs(db_session_mock, mocker):
    mock_get_logs = mocker.patch("app.services.audit_service.audit_repository.get_logs")
    mock_get_logs.return_value = ["log1", "log2"]
    start = date(2023, 1, 1)
    end = date(2023, 12, 31)
    result = audit_service.get_logs(
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
