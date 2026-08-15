from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.main import app
from app.schemas.token import Token


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
def client(mock_active_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_active_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_login_access_token_endpoint(client: TestClient, mocker: MagicMock) -> None:
    expected_token = Token(access_token="mocked_token", token_type="bearer")
    mocker.patch(
        "app.api.v1.auth.auth_service.authenticate",
        return_value=expected_token,
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
