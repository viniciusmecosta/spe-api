from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.domain.enums import RecordType, UserRole
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_schemas import TimeRecordTimelineResponse
from app.features.users.user_models import User
from app.main import app


@pytest.fixture
def mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MANAGER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_user
    app.dependency_overrides[deps.get_current_manager] = lambda: mock_user
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_register_entry(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 8, 0, 0)
    mock_record = TimeRecord(
        id=1,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        created_at=now,
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.register_entry",
        return_value=mock_record,
    )

    response = client.post("/api/v1/time-records/entry")
    assert response.status_code == 201
    assert response.json()["record_type"] == "ENTRY"


def test_register_exit(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 18, 0, 0)
    mock_record = TimeRecord(
        id=2,
        user_id=1,
        record_type=RecordType.EXIT,
        record_datetime=now,
        created_at=now,
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.register_exit",
        return_value=mock_record,
    )

    response = client.post("/api/v1/time-records/exit")
    assert response.status_code == 201
    assert response.json()["record_type"] == "EXIT"


def test_toggle_record_type(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 18, 0, 0)
    mock_record = TimeRecord(
        id=1,
        user_id=1,
        record_type=RecordType.EXIT,
        record_datetime=now,
        created_at=now,
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.toggle_record_type",
        return_value=mock_record,
    )

    response = client.put("/api/v1/time-records/1/toggle")
    assert response.status_code == 200
    assert response.json()["record_type"] == "EXIT"


def test_read_my_records(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 8, 0, 0)
    mock_record = TimeRecord(
        id=1,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        created_at=now,
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.get_my_records",
        return_value=[mock_record],
    )

    response = client.get("/api/v1/time-records/my")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_records_for_admin(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 8, 0, 0)
    mock_record = TimeRecord(
        id=1,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        created_at=now,
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.list_records_for_admin",
        return_value=[mock_record],
    )

    response = client.get("/api/v1/time-records/admin/list?user_id=1&start_date=2026-08-01T00:00:00&end_date=2026-08-31T23:59:59")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_time_record_admin(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 8, 0, 0)
    mock_record = TimeRecord(
        id=1,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        created_at=now,
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.create_admin_record",
        return_value=mock_record,
    )

    response = client.post(
        "/api/v1/time-records/admin",
        json={"user_id": 1, "record_type": "ENTRY", "record_datetime": "2026-08-14T08:00:00", "edit_justification": "Admin insert"},
    )
    assert response.status_code == 201


def test_update_time_record_admin(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 8, 0, 0)
    mock_record = TimeRecord(
        id=1,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        created_at=now,
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.update_admin_record",
        return_value=mock_record,
    )

    response = client.put(
        "/api/v1/time-records/admin/1",
        json={"record_type": "ENTRY", "record_datetime": "2026-08-14T08:00:00", "edit_justification": "Admin edit"},
    )
    assert response.status_code == 200


def test_delete_time_record_admin(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch("app.features.time_records.time_record_router.time_record_service.delete_admin_record")

    response = client.request(
        "DELETE",
        "/api/v1/time-records/admin/1",
        json={"edit_justification": "Admin delete"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_get_time_record_timeline(client: TestClient, mocker: MagicMock) -> None:
    now = datetime(2026, 8, 14, 8, 0, 0)
    timeline_item = TimeRecordTimelineResponse(
        id=1,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        created_at=now,
        is_ignored=False,
        short_id="test_id"
    )
    mocker.patch(
        "app.features.time_records.time_record_router.time_record_service.get_record_timeline",
        return_value=[timeline_item],
    )

    response = client.get("/api/v1/time-records/1/timeline")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_trigger_tolerance_cron(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch("app.features.time_records.time_record_router.tolerance_cron_service.process_unverified_entries")

    response = client.post("/api/v1/time-records/admin/tolerance/process")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
