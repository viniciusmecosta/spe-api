import hashlib
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Request

from app.core.config import settings

ALGORITHM = settings.ALGORITHM


def create_access_token(subject: str | Any, name: str | None = None,
                        expires_delta: timedelta | None = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject)}
    if name:
        to_encode["name"] = name
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def get_api_key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _resolve_device_name_from_ip(ip: str) -> str:
    if ip in ("127.0.0.1", "::1", "localhost", "0.0.0.0"):
        try:
            return socket.gethostname()
        except Exception:
            return ""
    return ""


def get_client_device_name(ip: str | None = None, request: Request | None = None) -> str:
    device_name = ""

    if request is not None:
        if hasattr(request, "state"):
            state_name = getattr(request.state, "device_name", "")
            if isinstance(state_name, str) and state_name:
                device_name = state_name
        if not device_name and hasattr(request, "headers"):
            device_name = request.headers.get("X-Device-Name", "")
        if isinstance(device_name, str) and device_name.lower() == "localhost":
            device_name = ""

    if not device_name and ip:
        device_name = _resolve_device_name_from_ip(ip)

    if not device_name or (isinstance(device_name, str) and device_name.lower() == "localhost"):
        device_name = "Desconhecido"

    return device_name[:255]
