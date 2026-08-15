from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.main import app
from app.schemas.routine_log import RoutineLogResponse


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
    mocker.patch(
        "app.api.v1.routine_logs.routine_log_service.get_logs",
        return_value=expected,
    )

    response = client.get("/api/v1/routine-logs/?routine_type=BACKUP&status=SUCCESS")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["routine_type"] == "BACKUP"
