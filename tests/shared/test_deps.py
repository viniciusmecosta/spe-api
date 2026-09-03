from unittest.mock import MagicMock, patch

import jwt
from fastapi import HTTPException

import pytest
from app.core.security import get_api_key_hash
from app.features.devices.device_models import DeviceCredential
from app.shared.deps import (
    get_db,
    get_current_user,
    get_current_active_user,
    get_current_manager,
    get_current_maintainer,
    verify_device_api_key,
    verify_consumer_api_key,
)
from app.shared.enums import UserRole, DeviceKeyType


def test_get_db():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass


@pytest.mark.asyncio
async def test_get_current_user_invalid_jwt():
    db = MagicMock()
    with patch("jwt.decode", side_effect=jwt.PyJWTError("jwt error")):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db, "invalid_token")
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_no_sub():
    db = MagicMock()
    with patch("jwt.decode", return_value={}):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db, "valid_jwt_no_sub")
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_not_found(db_session):
    with patch("jwt.decode", return_value={"sub": "999999"}):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db_session, "valid_jwt_non_existent")
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_current_user_success(db_session, normal_user):
    with patch("jwt.decode", return_value={"sub": str(normal_user.id)}):
        user = await get_current_user(db_session, "token")
        assert user.id == normal_user.id


def test_get_current_active_user():
    user = MagicMock()
    user.is_active = False
    with pytest.raises(HTTPException) as exc_info:
        get_current_active_user(user)
    assert exc_info.value.status_code == 400

    active_user = MagicMock()
    active_user.is_active = True
    assert get_current_active_user(active_user) == active_user


def test_get_current_manager_forbidden():
    user = MagicMock()
    user.role = UserRole.EMPLOYEE
    with pytest.raises(HTTPException) as exc_info:
        get_current_manager(user)
    assert exc_info.value.status_code == 403


def test_get_current_manager_success():
    user = MagicMock()
    user.role = UserRole.MANAGER
    assert get_current_manager(user) == user


def test_get_current_maintainer_forbidden():
    user = MagicMock()
    user.role = UserRole.MANAGER
    with pytest.raises(HTTPException) as exc_info:
        get_current_maintainer(user)
    assert exc_info.value.status_code == 403


def test_get_current_maintainer_success():
    user = MagicMock()
    user.role = UserRole.MAINTAINER
    assert get_current_maintainer(user) == user


@pytest.mark.asyncio
async def test_verify_device_api_key_none(db_session):
    req = MagicMock()
    db = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await verify_device_api_key(req, None, db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_device_api_key_invalid(db_session):
    req = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await verify_device_api_key(req, "invalid_key", db_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_device_api_key_success(db_session):
    req = MagicMock()
    raw_key = "valid_device_key_deps_test"
    hashed = get_api_key_hash(raw_key)
    cred = DeviceCredential(name="Relogio Dep", api_key_hash=hashed, key_type=DeviceKeyType.DEVICE, is_active=True)
    db_session.add(cred)
    db_session.commit()

    device = await verify_device_api_key(req, raw_key, db_session)
    assert device.name == "Relogio Dep"
    assert req.state.device_name == "Relogio Dep"


@pytest.mark.asyncio
async def test_verify_consumer_api_key_none(db_session):
    req = MagicMock()
    db = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await verify_consumer_api_key(req, None, db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_consumer_api_key_invalid(db_session):
    req = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await verify_consumer_api_key(req, "invalid_key", db_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_consumer_api_key_success(db_session):
    req = MagicMock()
    raw_key = "valid_consumer_key_deps_test"
    hashed = get_api_key_hash(raw_key)
    cred = DeviceCredential(name="Servidor Dep", api_key_hash=hashed, key_type=DeviceKeyType.CONSUMER, is_active=True)
    db_session.add(cred)
    db_session.commit()

    consumer = await verify_consumer_api_key(req, raw_key, db_session)
    assert consumer.name == "Servidor Dep"
    assert req.state.device_name == "Servidor Dep"


@pytest.mark.asyncio
async def test_get_current_user_async_db_awaitable(normal_user):
    from unittest.mock import AsyncMock
    async_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.first.return_value = normal_user
    async_db.scalars = AsyncMock(return_value=mock_res)
    with patch("jwt.decode", return_value={"sub": str(normal_user.id)}):
        u = await get_current_user(async_db, "token")
        assert u.id == normal_user.id


@pytest.mark.asyncio
async def test_get_current_user_legacy_sync_query(normal_user):
    sync_db = MagicMock()
    del sync_db.scalars
    sync_db.query.return_value.options.return_value.filter.return_value.first.return_value = normal_user
    with patch("jwt.decode", return_value={"sub": str(normal_user.id)}):
        u = await get_current_user(sync_db, "token")
        assert u.id == normal_user.id


@pytest.mark.asyncio
async def test_verify_keys_async_and_sync():
    from unittest.mock import AsyncMock
    from app.features.devices.device_models import DeviceCredential
    dev = DeviceCredential(name="D1", api_key_hash="hash", key_type=DeviceKeyType.DEVICE, is_active=True)
    req = MagicMock()

    async_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.first.return_value = dev
    async_db.scalars = AsyncMock(return_value=mock_res)
    with patch("app.shared.deps.get_api_key_hash", return_value="hash"):
        res = await verify_device_api_key(req, "key", async_db)
        assert res == dev

    sync_db = MagicMock()
    del sync_db.scalars
    sync_db.query.return_value.filter.return_value.first.return_value = dev
    with patch("app.shared.deps.get_api_key_hash", return_value="hash"):
        res = await verify_device_api_key(req, "key", sync_db)
        assert res == dev

    consumer = DeviceCredential(name="C1", api_key_hash="hash", key_type=DeviceKeyType.CONSUMER, is_active=True)
    mock_res_c = MagicMock()
    mock_res_c.first.return_value = consumer
    async_db.scalars = AsyncMock(return_value=mock_res_c)
    with patch("app.shared.deps.get_api_key_hash", return_value="hash"):
        res_c = await verify_consumer_api_key(req, "key", async_db)
        assert res_c == consumer

    sync_db.query.return_value.filter.return_value.first.return_value = consumer
    with patch("app.shared.deps.get_api_key_hash", return_value="hash"):
        res_cs = await verify_consumer_api_key(req, "key", sync_db)
        assert res_cs == consumer
