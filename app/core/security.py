import bcrypt
import socket
from datetime import datetime, timedelta
from fastapi import Request
from jose import jwt
from typing import Any, Union

from app.core.config import settings

ALGORITHM = settings.ALGORITHM


def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject)}
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


def get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "127.0.0.1"


def get_client_device_name(ip: str) -> str:
    if not ip:
        return "Unknown"
    if ip in ("127.0.0.1", "::1"):
        return "localhost"
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "Unknown"
