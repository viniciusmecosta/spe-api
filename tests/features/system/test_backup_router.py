from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.system.audit_service import AuditService
from app.features.system.routine_orchestrator import RoutineOrchestrator
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


def test_trigger_manual_backup_success(client: TestClient, mocker: MagicMock) -> None:
    mock_send = mocker.patch.object(
        RoutineOrchestrator,
        "send_manual_backup_email",
        return_value=True,
    )
    mock_audit = mocker.patch.object(AuditService, "async_log", new_callable=AsyncMock)

    response = client.post("/api/v1/backup/trigger")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "segundo plano" in data["message"]
    mock_audit.assert_awaited_once()


def test_trigger_manual_backup_forbidden_for_employee(db_session_mock: MagicMock) -> None:
    employee_user = MagicMock(spec=User)
    employee_user.id = 2
    employee_user.role = UserRole.EMPLOYEE
    employee_user.is_active = True

    app.dependency_overrides[deps.get_current_active_user] = lambda: employee_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)

    response = client.post("/api/v1/backup/trigger")
    assert response.status_code == 403
    app.dependency_overrides.clear()
