import jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session
from typing import Generator

from app.core.config import settings
from app.core.security import verify_password
from app.database.session import SessionLocal
from app.domain.models.device import DeviceCredential
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.schemas.token import TokenPayload

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def get_current_user(
        db: Session = Depends(get_db),
        token: str = Depends(reusable_oauth2)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    user = db.query(User).filter(User.id == int(token_data.sub)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_current_active_user(
        current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def get_current_manager(
        current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges (Manager or Maintainer required)"
        )
    return current_user


def get_current_maintainer(
        current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.role != UserRole.MAINTAINER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges (Maintainer required)"
        )
    return current_user


async def verify_device_api_key(
        x_device_id: str = Header(..., description="Device Identifier"),
        x_api_key: str = Header(..., description="Device API Key"),
        db: Session = Depends(get_db)
):
    device = db.query(DeviceCredential).filter(DeviceCredential.device_id == x_device_id).first()
    if not device or not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device not found or inactive"
        )

    if not verify_password(x_api_key, device.api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key"
        )

    return device


async def verify_consumer_api_key(
        x_consumer_id: str = Header(..., description="Consumer Identifier"),
        x_consumer_api_key: str = Header(..., description="Consumer API Key"),
        db: Session = Depends(get_db)
):
    consumer = db.query(DeviceCredential).filter(DeviceCredential.device_id == x_consumer_id).first()
    if not consumer or not consumer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consumer not found or inactive"
        )

    if not verify_password(x_consumer_api_key, consumer.api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Consumer API Key"
        )

    return consumer
