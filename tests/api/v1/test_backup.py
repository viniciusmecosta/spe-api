from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.shared.enums import UserRole
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


def test_trigger_manual_backup_success(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.system.system_router.routine_orchestrator.send_manual_backup_email",
        return_value=True,
    )

    response = client.post("/api/v1/backup/trigger")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "sucesso" in data["message"]


def test_trigger_manual_backup_failure(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch(
        "app.features.system.system_router.routine_orchestrator.send_manual_backup_email",
        return_value=False,
    )

    response = client.post("/api/v1/backup/trigger")
    assert response.status_code == 400
    assert "Falha ao gerar ou enviar o backup" in response.json()["detail"]
