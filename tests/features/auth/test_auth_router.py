from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pytest
from app.database.session import get_async_db
from app.features.auth.auth_schemas import Token
from app.features.auth.auth_service import AuthService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def async_db_mock():
    session = MagicMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_active_user() -> User:
    user = User(
        id=1,
        name="Test User",
        username="testuser",
        role=UserRole.MANAGER,
        is_active=True,
        email="test@example.com",
    )
    return user

@pytest.fixture
def client(mock_active_user: User, async_db_mock: AsyncMock) -> TestClient:
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_active_user
    app.dependency_overrides[get_async_db] = lambda: async_db_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

def test_login_access_token_endpoint(client: TestClient, mocker: MagicMock) -> None:
    expected_token = Token(access_token="mocked_token", token_type="bearer")
    mocker.patch.object(
        AuthService, "authenticate", new_callable=AsyncMock, return_value=expected_token
    )

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "mocked_token"
    assert data["token_type"] == "bearer"

def test_read_users_me_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["name"] == "Test User"
