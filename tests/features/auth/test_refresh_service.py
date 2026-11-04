from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.auth.auth_exceptions import InvalidCredentialsError
from app.features.auth.auth_repository import auth_repository
from app.features.auth.auth_service import AuthService


@pytest.fixture
def refresh_user():
    return SimpleNamespace(
        id=1,
        auth_version=2,
        name="Employee",
        is_active=True,
        password_change_required=False,
        password_hash="hashed",
    )


@pytest.fixture
def refresh_record():
    return SimpleNamespace(
        user_id=1,
        auth_version=2,
        family_id="f" * 32,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        revoked_at=None,
        used_at=None,
    )


@pytest.mark.parametrize(
    "invalid",
    ["missing_user", "revoked", "used", "expired", "inactive", "required", "version"],
)
async def test_refresh_invalidates_family(
    async_db_mock, refresh_user, refresh_record, mocker, invalid
):
    if invalid == "missing_user":
        refresh_user = None
    elif invalid == "revoked":
        refresh_record.revoked_at = datetime.now(UTC)
    elif invalid == "used":
        refresh_record.used_at = datetime.now(UTC)
    elif invalid == "expired":
        refresh_record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif invalid == "inactive":
        refresh_user.is_active = False
    elif invalid == "required":
        refresh_user.password_change_required = True
    else:
        refresh_record.auth_version = 1
    mocker.patch.object(
        auth_repository,
        "find_refresh",
        new_callable=AsyncMock,
        return_value=refresh_record,
    )
    mocker.patch.object(
        auth_repository, "lock_user", new_callable=AsyncMock, return_value=refresh_user
    )
    revoke = mocker.patch.object(
        auth_repository, "revoke_family", new_callable=AsyncMock
    )
    service = AuthService(async_db_mock)
    with pytest.raises(InvalidCredentialsError):
        await service.refresh("secret")
    revoke.assert_awaited_once()
    async_db_mock.commit.assert_awaited_once()


async def test_unknown_refresh_is_rejected(async_db_mock, mocker):
    mocker.patch.object(
        auth_repository, "find_refresh", new_callable=AsyncMock, return_value=None
    )
    service = AuthService(async_db_mock)
    with pytest.raises(InvalidCredentialsError):
        await service.refresh("unknown")
    async_db_mock.commit.assert_not_awaited()


@pytest.mark.parametrize("missing", [False, True])
async def test_password_change_rejects_stale_user(
    async_db_mock, refresh_user, mocker, missing
):
    current = SimpleNamespace(id=1, auth_version=1)
    mocker.patch.object(
        auth_repository,
        "lock_user",
        new_callable=AsyncMock,
        return_value=None if missing else refresh_user,
    )
    service = AuthService(async_db_mock)
    with pytest.raises(InvalidCredentialsError):
        await service.change_password(current, "old", "new")


async def test_utc_preserves_aware_and_assigns_naive():
    naive = datetime(2026, 1, 1)
    aware = naive.replace(tzinfo=UTC)
    assert AuthService._utc(naive) == aware
    assert AuthService._utc(aware) is aware


async def test_refresh_disappearing_after_lock_is_rejected(
    async_db_mock, refresh_record, mocker
):
    mocker.patch.object(
        auth_repository,
        "find_refresh",
        new_callable=AsyncMock,
        side_effect=[refresh_record, None],
    )
    mocker.patch.object(auth_repository, "lock_user", new_callable=AsyncMock)
    service = AuthService(async_db_mock)
    with pytest.raises(InvalidCredentialsError):
        await service.refresh("expired-and-purged")


async def test_refresh_rotates_credential(
    async_db_mock, refresh_user, refresh_record, mocker
):
    mocker.patch.object(
        auth_repository,
        "find_refresh",
        new_callable=AsyncMock,
        return_value=refresh_record,
    )
    mocker.patch.object(
        auth_repository, "lock_user", new_callable=AsyncMock, return_value=refresh_user
    )
    result = await AuthService(async_db_mock).refresh("secret")
    assert result.refresh_token
    assert refresh_record.used_at is not None
    async_db_mock.add.assert_called_once()
    async_db_mock.commit.assert_awaited_once()


@pytest.mark.parametrize("exists", [True, False])
async def test_logout_revokes_known_family(
    async_db_mock, refresh_record, mocker, exists
):
    mocker.patch.object(
        auth_repository,
        "find_refresh",
        new_callable=AsyncMock,
        return_value=refresh_record if exists else None,
    )
    lock = mocker.patch.object(auth_repository, "lock_user", new_callable=AsyncMock)
    revoke = mocker.patch.object(
        auth_repository, "revoke_family", new_callable=AsyncMock
    )
    await AuthService(async_db_mock).logout("secret")
    assert revoke.await_count == int(exists)
    assert lock.await_count == int(exists)


async def test_password_change_issues_new_session(async_db_mock, refresh_user, mocker):
    mocker.patch.object(
        auth_repository, "lock_user", new_callable=AsyncMock, return_value=refresh_user
    )
    mocker.patch(
        "app.features.auth.auth_service.security.verify_password",
        side_effect=[True, False],
    )
    mocker.patch(
        "app.features.auth.auth_service.security.get_password_hash",
        return_value="new_hash",
    )
    revoke = mocker.patch.object(auth_repository, "revoke_user", new_callable=AsyncMock)
    token = await AuthService(async_db_mock).change_password(
        refresh_user, "old-password", "new-password"
    )
    assert token.refresh_token
    assert refresh_user.auth_version == 3
    assert refresh_user.password_hash == "new_hash"
    assert refresh_user.password_change_required is False
    revoke.assert_awaited_once()


def test_sync_user_reset_requirement_revokes_existing_access(db_session, normal_user):
    from app.features.users.user_repository import user_repository

    version = normal_user.auth_version
    updated = user_repository.update(
        db_session, db_obj=normal_user, obj_in={"password_change_required": True}
    )
    assert updated.password_change_required is True
    assert updated.auth_version == version + 1


async def test_auth_repository_methods_and_password_change_branches(
    async_db_mock, refresh_user, mocker
):
    from unittest.mock import MagicMock

    from app.core.exceptions import DomainException
    from app.features.users.user_repository import async_user_repository

    now = datetime.now(UTC)
    async_db_mock.scalar.return_value = None
    assert await auth_repository.find_refresh(async_db_mock, "h") is None
    assert await auth_repository.lock_user(async_db_mock, 1) is None
    await auth_repository.revoke_family(async_db_mock, "fam", now)
    await auth_repository.revoke_user(async_db_mock, 1, now)
    async_db_mock.execute.return_value = SimpleNamespace(rowcount=3)
    assert await auth_repository.purge_expired(async_db_mock, now, 10) == 3

    service = AuthService(async_db_mock)
    refresh_user.password_change_required = True
    token = service._issue_tokens(refresh_user)
    assert token.password_change_required is True
    assert token.refresh_token is None

    refresh_user.password_change_required = False
    mocker.patch.object(
        auth_repository, "lock_user", new_callable=AsyncMock, return_value=refresh_user
    )
    mocker.patch(
        "app.features.auth.auth_service.security.verify_password",
        return_value=False,
    )
    with pytest.raises(InvalidCredentialsError):
        await service.change_password(refresh_user, "wrong", "new-password")

    mocker.patch(
        "app.features.auth.auth_service.security.verify_password",
        side_effect=[True, True],
    )
    with pytest.raises(DomainException):
        await service.change_password(refresh_user, "same", "same")

    mocker.patch.object(
        async_user_repository, "get", new_callable=AsyncMock, return_value=refresh_user
    )
    db_user = MagicMock()
    db_user.id = 1
    db_user.auth_version = 1
    await async_user_repository.update(
        async_db_mock, db_obj=db_user, obj_in={"password_change_required": True}
    )
    assert db_user.password_change_required is True
