import bcrypt
import jwt
import socket
from datetime import datetime, timedelta
from fastapi import Request
from typing import Any, Union, Optional

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
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def get_client_device_name(ip: str, request: Optional[Request] = None) -> str:
    device_name = ""

    if request:
        device_name = request.headers.get("X-Device-Name", "")
        if device_name.lower() == "localhost":
            device_name = ""

    if not device_name and ip:
        if ip in ("127.0.0.1", "::1", "localhost", "0.0.0.0"):
            try:
                device_name = socket.gethostname()
            except Exception:
                pass
        else:
            try:
                socket.setdefaulttimeout(1.5)
                host_info = socket.gethostbyaddr(ip)
                if host_info and host_info[0]:
                    device_name = host_info[0].split('.')[0]
            except Exception:
                pass

    if not device_name or device_name.lower() == "localhost":
        device_name = "Desconhecido"

    return device_name[:255]
