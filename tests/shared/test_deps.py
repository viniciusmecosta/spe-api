from unittest.mock import MagicMock, patch
import pytest
import jwt
from fastapi import HTTPException

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
from app.features.devices.device_models import DeviceCredential
from app.core.security import get_api_key_hash


def test_get_db():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass


def test_get_current_user_invalid_jwt():
    db = MagicMock()
    with patch("jwt.decode", side_effect=jwt.PyJWTError("jwt error")):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(db, "invalid_token")
        assert exc_info.value.status_code == 401


def test_get_current_user_no_sub():
    db = MagicMock()
    with patch("jwt.decode", return_value={}):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(db, "valid_jwt_no_sub")
        assert exc_info.value.status_code == 401


def test_get_current_user_not_found(db_session):
    with patch("jwt.decode", return_value={"sub": "999999"}):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(db_session, "valid_jwt_non_existent")
        assert exc_info.value.status_code == 404


def test_get_current_user_success(db_session, normal_user):
    with patch("jwt.decode", return_value={"sub": str(normal_user.id)}):
        user = get_current_user(db_session, "token")
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


def test_verify_device_api_key_none(db_session):
    req = MagicMock()
    db = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        verify_device_api_key(req, None, db)
    assert exc_info.value.status_code == 401


def test_verify_device_api_key_invalid(db_session):
    req = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        verify_device_api_key(req, "invalid_key", db_session)
    assert exc_info.value.status_code == 401


def test_verify_device_api_key_success(db_session):
    req = MagicMock()
    raw_key = "valid_device_key_deps_test"
    hashed = get_api_key_hash(raw_key)
    cred = DeviceCredential(name="Relogio Dep", api_key_hash=hashed, key_type=DeviceKeyType.DEVICE, is_active=True)
    db_session.add(cred)
    db_session.commit()

    device = verify_device_api_key(req, raw_key, db_session)
    assert device.name == "Relogio Dep"
    assert req.state.device_name == "Relogio Dep"


def test_verify_consumer_api_key_none(db_session):
    req = MagicMock()
    db = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        verify_consumer_api_key(req, None, db)
    assert exc_info.value.status_code == 401


def test_verify_consumer_api_key_invalid(db_session):
    req = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        verify_consumer_api_key(req, "invalid_key", db_session)
    assert exc_info.value.status_code == 401


def test_verify_consumer_api_key_success(db_session):
    req = MagicMock()
    raw_key = "valid_consumer_key_deps_test"
    hashed = get_api_key_hash(raw_key)
    cred = DeviceCredential(name="Servidor Dep", api_key_hash=hashed, key_type=DeviceKeyType.CONSUMER, is_active=True)
    db_session.add(cred)
    db_session.commit()

    consumer = verify_consumer_api_key(req, raw_key, db_session)
    assert consumer.name == "Servidor Dep"
    assert req.state.device_name == "Servidor Dep"
