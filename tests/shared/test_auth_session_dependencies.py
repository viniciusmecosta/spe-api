from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.shared.deps import get_current_user, get_password_change_user


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("restricted", 403),
        ("finished_reset", 401),
        ("revoked", 401),
        ("active_session", 200),
        ("inactive", 400),
    ],
)
async def test_authentication_session_constraints(
    async_db_mock, mocker, scenario, expected
):
    user = SimpleNamespace(
        id=1,
        auth_version=0,
        is_active=scenario != "inactive",
        password_change_required=scenario == "restricted",
    )
    result = MagicMock()
    result.first.return_value = user
    async_db_mock.scalars = AsyncMock(return_value=result)
    async_db_mock.scalar = AsyncMock(
        return_value=1 if scenario == "active_session" else None
    )
    purpose = (
        "password_change" if scenario in ("restricted", "finished_reset") else "access"
    )
    payload = {"sub": "1", "purpose": purpose}
    if scenario in ("revoked", "active_session"):
        payload["sid"] = "a" * 32
    mocker.patch("app.shared.deps.jwt.decode", return_value=payload)
    if expected == 200:
        assert await get_current_user(async_db_mock, "token") is user
    else:
        with pytest.raises(HTTPException) as error:
            await get_current_user(async_db_mock, "token")
        assert error.value.status_code == expected


async def test_password_change_user_accepts_restricted_credential(
    async_db_mock, mocker
):
    user = SimpleNamespace(
        id=1, auth_version=0, is_active=True, password_change_required=True
    )
    result = MagicMock()
    result.first.return_value = user
    async_db_mock.scalars = AsyncMock(return_value=result)
    mocker.patch(
        "app.shared.deps.jwt.decode",
        return_value={"sub": "1", "purpose": "password_change"},
    )
    assert await get_password_change_user(async_db_mock, "token") is user
