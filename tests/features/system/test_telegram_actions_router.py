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


def test_trigger_manual_backup(client: TestClient, mocker: MagicMock) -> None:
    mock_task = mocker.patch.object(RoutineOrchestrator, "execute_manual_backup_telegram")
    mock_audit = mocker.patch.object(AuditService, "async_log", new_callable=AsyncMock)

    response = client.post("/api/v1/telegram/manual-backup")
    assert response.status_code == 200
    assert "Telegram" in response.json()["message"]
    mock_audit.assert_awaited_once()


def test_trigger_manual_report_success(client: TestClient, mocker: MagicMock) -> None:
    mock_task = mocker.patch.object(RoutineOrchestrator, "send_manual_report_telegram")
    mock_audit = mocker.patch.object(AuditService, "async_log", new_callable=AsyncMock)

    response = client.post("/api/v1/telegram/manual-report?start_date=2026-08-01&end_date=2026-08-05")
    assert response.status_code == 200
    assert "processamento em background" in response.json()["message"]
    mock_audit.assert_awaited_once()


def test_trigger_manual_report_start_after_end(client: TestClient) -> None:
    response = client.post("/api/v1/telegram/manual-report?start_date=2026-08-10&end_date=2026-08-05")
    assert response.status_code == 400
    assert "A data de início não pode ser maior" in response.json()["detail"]


def test_trigger_manual_report_period_exceeded(client: TestClient) -> None:
    response = client.post("/api/v1/telegram/manual-report?start_date=2026-08-01&end_date=2026-08-15")
    assert response.status_code == 400
    assert "Período excedido" in response.json()["detail"]
