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

    req_with_state = MagicMock(spec=Request)
    req_with_state.state = MagicMock()
    req_with_state.state.device_name = "Device-From-State"
    req_with_state.headers.get.side_effect = lambda k, d="": "HeaderDevice" if k == "X-Device-Name" else d
    assert get_client_device_name("192.168.1.50", req_with_state) == "Device-From-State"

    req_header_only = MagicMock(spec=Request)
    req_header_only.state = MagicMock()
    req_header_only.state.device_name = ""
    req_header_only.headers.get.side_effect = lambda k, d="": "HeaderDevice" if k == "X-Device-Name" else d
    assert get_client_device_name("192.168.1.50", req_header_only) == "HeaderDevice"

    with patch("socket.gethostname", side_effect=Exception("err")):
        assert _resolve_device_name_from_ip("127.0.0.1") == ""

    with patch("socket.gethostname", return_value="my-machine"):
        assert _resolve_device_name_from_ip("127.0.0.1") == "my-machine"

    assert _resolve_device_name_from_ip("192.168.1.100") == ""

    mock_req_lh = MagicMock()
    mock_req_lh.headers = {"X-Device-Name": "localhost"}
    assert get_client_device_name(None, mock_req_lh) == "Desconhecido"
    assert get_client_device_name("192.168.1.43", None) == "Desconhecido"
