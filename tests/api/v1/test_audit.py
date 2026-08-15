from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.main import app
from app.schemas.audit import AuditLogResponse


@pytest.fixture
def mock_manager_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MANAGER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_manager_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_manager] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_read_audit_logs(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        AuditLogResponse(
            id=1,
            user_id=1,
            action="CREATE",
            entity="USER",
            entity_id=2,
            old_data=None,
            new_data={"name": "Novo"},
            timestamp=datetime(2026, 8, 14, 10, 0, 0),
        )
    ]
    mocker.patch(
        "app.api.v1.audit.audit_service.get_logs",
        return_value=expected,
    )

    response = client.get("/api/v1/audit/?action=CREATE&order_by=desc")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["action"] == "CREATE"
