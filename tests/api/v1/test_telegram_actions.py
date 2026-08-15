from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.domain.enums import UserRole
from app.features.users.user_models import User
from app.main import app


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
    mock_task = mocker.patch("app.features.system.system_router.routine_orchestrator.execute_manual_backup_telegram")

    response = client.post("/api/v1/telegram/manual-backup")
    assert response.status_code == 200
    assert "Telegram" in response.json()["message"]


def test_trigger_manual_report_success(client: TestClient, mocker: MagicMock) -> None:
    mock_task = mocker.patch("app.features.system.system_router.routine_orchestrator.send_manual_report_telegram")

    response = client.post("/api/v1/telegram/manual-report?start_date=2026-08-01&end_date=2026-08-05")
    assert response.status_code == 200
    assert "processamento em background" in response.json()["message"]


def test_trigger_manual_report_start_after_end(client: TestClient) -> None:
    response = client.post("/api/v1/telegram/manual-report?start_date=2026-08-10&end_date=2026-08-05")
    assert response.status_code == 400
    assert "A data de início não pode ser maior" in response.json()["detail"]


def test_trigger_manual_report_period_exceeded(client: TestClient) -> None:
    response = client.post("/api/v1/telegram/manual-report?start_date=2026-08-01&end_date=2026-08-15")
    assert response.status_code == 400
    assert "Período excedido" in response.json()["detail"]
