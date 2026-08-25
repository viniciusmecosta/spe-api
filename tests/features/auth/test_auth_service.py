from unittest.mock import AsyncMock, MagicMock

import pytest
from app.features.auth.auth_exceptions import InactiveUserError, InvalidCredentialsError
from app.features.auth.auth_service import AuthService
from app.features.users.user_models import User
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


@pytest.mark.asyncio
async def test_authenticate_user_not_found(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.auth.auth_service.async_user_repository.get_by_username", new_callable=AsyncMock,
                 return_value=None)
    auth_service = AuthService(async_db_mock)

    with pytest.raises(InvalidCredentialsError) as exc_info:
        await auth_service.authenticate("unknown", "pass123")
    assert exc_info.value.status_code == 401
    assert "Usuário ou senha incorretos." in exc_info.value.detail


@pytest.mark.asyncio
async def test_authenticate_password_mismatch(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.role = UserRole.MANAGER
    user.password_hash = "hashed"
    mocker.patch("app.features.auth.auth_service.async_user_repository.get_by_username", new_callable=AsyncMock,
                 return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "prod")
    mocker.patch("app.features.auth.auth_service.security.verify_password", return_value=False)
    auth_service = AuthService(async_db_mock)

    with pytest.raises(InvalidCredentialsError) as exc_info:
        await auth_service.authenticate("admin", "wrongpass")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_inactive_user(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.role = UserRole.MANAGER
    user.password_hash = "hashed"
    user.is_active = False
    mocker.patch("app.features.auth.auth_service.async_user_repository.get_by_username", new_callable=AsyncMock,
                 return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "prod")
    mocker.patch("app.features.auth.auth_service.security.verify_password", return_value=True)
    auth_service = AuthService(async_db_mock)

    with pytest.raises(InactiveUserError) as exc_info:
        await auth_service.authenticate("admin", "correctpass")
    assert exc_info.value.status_code == 400
    assert "Usuário inativo." in exc_info.value.detail


@pytest.mark.asyncio
async def test_authenticate_dev_bypass_success(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.id = 10
    user.name = "Dev User"
    user.role = UserRole.EMPLOYEE
    user.is_active = True
    mocker.patch("app.features.auth.auth_service.async_user_repository.get_by_username", new_callable=AsyncMock,
                 return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "dev")
    mocker.patch("app.features.auth.auth_service.security.create_access_token", return_value="fake_token")
    mocker.patch("app.features.auth.auth_service.audit_service.async_log", new_callable=AsyncMock)
    auth_service = AuthService(async_db_mock)

    token = await auth_service.authenticate("dev_employee", "anypass")
    assert token.access_token == "fake_token"
    assert token.token_type == "bearer"


@pytest.mark.asyncio
async def test_authenticate_success(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.name = "Manager User"
    user.role = UserRole.MANAGER
    user.password_hash = "hashed"
    user.is_active = True
    mocker.patch("app.features.auth.auth_service.async_user_repository.get_by_username", new_callable=AsyncMock,
                 return_value=user)
    mocker.patch("app.features.auth.auth_service.settings.ENVIRONMENT", "prod")
    mocker.patch("app.features.auth.auth_service.security.verify_password", return_value=True)
    mocker.patch("app.features.auth.auth_service.security.create_access_token", return_value="prod_token")
    mocker.patch("app.features.auth.auth_service.audit_service.async_log", new_callable=AsyncMock)
    auth_service = AuthService(async_db_mock)

    token = await auth_service.authenticate("manager", "goodpass")
    assert token.access_token == "prod_token"
    assert token.token_type == "bearer"
