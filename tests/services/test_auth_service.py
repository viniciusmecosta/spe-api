from unittest.mock import MagicMock

from fastapi import HTTPException

import pytest
from app.shared.enums import UserRole
from app.features.auth.auth_service import auth_service
from app.features.users.user_models import User


def test_authenticate_user_not_found(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.auth.auth_service.user_repository.get_by_username", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate(db_session_mock, "unknown", "pass123")
    assert exc_info.value.status_code == 401
    assert "Incorrect username or password" in exc_info.value.detail


def test_authenticate_password_mismatch(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.role = UserRole.MANAGER
    user.password_hash = "hashed"
    mocker.patch("app.features.auth.auth_service.user_repository.get_by_username", return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "prod")
    mocker.patch("app.features.auth.auth_service.security.verify_password", return_value=False)

    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate(db_session_mock, "admin", "wrongpass")
    assert exc_info.value.status_code == 401


def test_authenticate_inactive_user(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.role = UserRole.MANAGER
    user.password_hash = "hashed"
    user.is_active = False
    mocker.patch("app.features.auth.auth_service.user_repository.get_by_username", return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "prod")
    mocker.patch("app.features.auth.auth_service.security.verify_password", return_value=True)

    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate(db_session_mock, "admin", "correctpass")
    assert exc_info.value.status_code == 400
    assert "Inactive user" in exc_info.value.detail


def test_authenticate_dev_bypass_success(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.id = 10
    user.name = "Dev User"
    user.role = UserRole.EMPLOYEE
    user.is_active = True
    mocker.patch("app.features.auth.auth_service.user_repository.get_by_username", return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "dev")
    mocker.patch("app.features.auth.auth_service.security.create_access_token", return_value="fake_token")
    mocker.patch("app.features.auth.auth_service.audit_service.log")

    token = auth_service.authenticate(db_session_mock, "dev_employee", "anypass")
    assert token.access_token == "fake_token"
    assert token.token_type == "bearer"


def test_authenticate_success(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.name = "Manager User"
    user.role = UserRole.MANAGER
    user.password_hash = "hashed"
    user.is_active = True
    mocker.patch("app.features.auth.auth_service.user_repository.get_by_username", return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "prod")
    mocker.patch("app.features.auth.auth_service.security.verify_password", return_value=True)
    mocker.patch("app.features.auth.auth_service.security.create_access_token", return_value="prod_token")
    mocker.patch("app.features.auth.auth_service.audit_service.log")

    token = auth_service.authenticate(db_session_mock, "manager", "goodpass")
    assert token.access_token == "prod_token"
    assert token.token_type == "bearer"
