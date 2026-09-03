from datetime import timedelta
from unittest.mock import MagicMock, patch

from fastapi import Request

from app.core.security import (
    _resolve_device_name_from_ip,
    create_access_token,
    get_client_device_name,
    get_client_ip,
    verify_password,
)


def test_create_access_token_custom_expire():
    token = create_access_token(subject="1", name="Test User", expires_delta=timedelta(hours=2))
    assert isinstance(token, str)


def test_verify_password_invalid():
    assert not verify_password("plain", "invalid_hash")


def test_get_client_ip_forwarded():
    req = MagicMock(spec=Request)
    req.headers.get.side_effect = lambda k: "203.0.113.195, 70.41.3.18" if k == "X-Forwarded-For" else None
    assert get_client_ip(req) == "203.0.113.195"


def test_get_client_device_name_cases():
    req = MagicMock(spec=Request)
    req.headers.get.side_effect = lambda k, d="": "localhost" if k == "X-Device-Name" else d
    res = get_client_device_name("127.0.0.1", req)
    assert isinstance(res, str)

    with patch("socket.gethostname", side_effect=Exception("err")):
        assert _resolve_device_name_from_ip("127.0.0.1") == ""

    with patch("socket.gethostbyaddr", return_value=("server.local", [], [])):
        assert _resolve_device_name_from_ip("192.168.1.100") == "server"

    with patch("socket.gethostbyaddr", return_value=("", [], [])):
        assert _resolve_device_name_from_ip("192.168.1.100") == ""

    with patch("socket.gethostbyaddr", side_effect=Exception("err")):
        assert _resolve_device_name_from_ip("192.168.1.100") == ""

    mock_req_lh = MagicMock()
    mock_req_lh.headers = {"X-Device-Name": "localhost"}
    assert get_client_device_name(None, mock_req_lh) == "Desconhecido"
