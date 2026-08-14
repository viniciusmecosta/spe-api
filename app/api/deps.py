from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_api_key_hash
from app.database.session import SessionLocal
from app.domain.models.device import DeviceCredential
from app.domain.models.enums import DeviceKeyType, UserRole
from app.domain.models.user import User
from app.schemas.token import TokenPayload

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)

api_key_header = APIKeyHeader(name="X-API-KEY", scheme_name="DeviceApiKey", auto_error=False)
consumer_api_key_header = APIKeyHeader(name="X-CONSUMER-API-KEY", scheme_name="ConsumerApiKey", auto_error=False)


def get_db() -> Generator[Session, None, None]:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(reusable_oauth2)],
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not token_data.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == int(str(token_data.sub))).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def get_current_manager(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges (Manager or Maintainer required)"
        )
    return current_user


def get_current_maintainer(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role != UserRole.MAINTAINER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges (Maintainer required)"
        )
    return current_user


def verify_device_api_key(
    request: Request,
    api_key: Annotated[str | None, Security(api_key_header)],
    db: Annotated[Session, Depends(get_db)],
) -> DeviceCredential:
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device API Key missing")

    hashed_key = get_api_key_hash(api_key)
    device = db.query(DeviceCredential).filter(
        DeviceCredential.api_key_hash == hashed_key,
        DeviceCredential.key_type == DeviceKeyType.DEVICE
    ).first()

    if not device or not device.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive Device API Key")

    request.state.device_name = device.name
    return device


def verify_consumer_api_key(
    request: Request,
    api_key: Annotated[str | None, Security(consumer_api_key_header)],
    db: Annotated[Session, Depends(get_db)],
) -> DeviceCredential:
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Consumer API Key missing")

    hashed_key = get_api_key_hash(api_key)
    consumer = db.query(DeviceCredential).filter(
        DeviceCredential.api_key_hash == hashed_key,
        DeviceCredential.key_type == DeviceKeyType.CONSUMER
    ).first()

    if not consumer or not consumer.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive Consumer API Key")

    request.state.device_name = consumer.name
    return consumer
