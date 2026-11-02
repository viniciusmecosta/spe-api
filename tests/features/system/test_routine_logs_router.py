from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.system.routine_log_service import RoutineLogService
from app.features.system.system_schemas import RoutineLogResponse
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def mock_maintainer_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MAINTAINER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_maintainer_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_read_routine_logs(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        RoutineLogResponse(
            id=1,
            routine_type="BACKUP",
            status="SUCCESS",
            execution_time=datetime(2026, 8, 14, 2, 0, 0),
            details="Backup OK",
        )
    ]
    mocker.patch.object(
        RoutineLogService,
        "get_logs",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.get("/api/v1/routine-logs/?routine_type=BACKUP&status=SUCCESS")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["routine_type"] == "BACKUP"


def test_job_and_monitoring_endpoints(client: TestClient, mocker: MagicMock) -> None:
    from app.features.system.job_service import JobService
    from app.features.system.operations_service import OperationsService

    mocker.patch.object(
        JobService,
        "get",
        new_callable=AsyncMock,
        return_value={
            "id": 1,
            "kind": "NOTIFICATION",
            "status": "SUCCESS",
            "attempts": 1,
            "created_at": datetime(2026, 8, 14, 2, 0, 0),
            "updated_at": datetime(2026, 8, 14, 2, 1, 0),
            "finished_at": datetime(2026, 8, 14, 2, 1, 0),
            "progress": {},
            "failures": [],
            "parts": [],
        },
    )
    mocker.patch.object(
        JobService,
        "retry",
        new_callable=AsyncMock,
        return_value={"job_id": "1", "status": "PENDING"},
    )
    mocker.patch.object(
        OperationsService,
        "readiness",
        new_callable=AsyncMock,
        return_value={"status": "ok", "database": "ok", "schema": "ok"},
    )
    mocker.patch.object(
        OperationsService,
        "snapshot",
        new_callable=AsyncMock,
        return_value={
            "status": "ok",
            "database": "ok",
            "schema": "ok",
            "version": "1.0.0",
            "environment": "test",
            "timezone": "UTC",
            "jobs": [],
            "oldest_pending_at": None,
            "routines": {},
            "recent_jobs": [],
        },
    )

    resp_get = client.get("/api/v1/routine-logs/jobs/1")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == 1

    resp_retry = client.post("/api/v1/routine-logs/jobs/1/retry")
    assert resp_retry.status_code == 200
    assert resp_retry.json()["status"] == "PENDING"

    resp_ready = client.get("/api/v1/ready")
    assert resp_ready.status_code == 200
    assert resp_ready.json()["status"] == "ok"

    resp_ops = client.get("/api/v1/operations")
    assert resp_ops.status_code == 200
    assert resp_ops.json()["database"] == "ok"
