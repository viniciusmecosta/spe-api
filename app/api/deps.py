import jwt
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from pydantic import ValidationError
from sqlalchemy.orm import Session
from typing import Generator

from app.core.config import settings
from app.core.security import get_api_key_hash
from app.database.session import SessionLocal
from app.domain.models.device import DeviceCredential
from app.domain.models.enums import UserRole, DeviceKeyType
from app.domain.models.user import User
from app.schemas.token import TokenPayload

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

api_key_header = APIKeyHeader(name="X-API-KEY", scheme_name="DeviceApiKey", auto_error=False)
consumer_api_key_header = APIKeyHeader(name="X-CONSUMER-API-KEY", scheme_name="ConsumerApiKey", auto_error=False)


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
        api_key: str = Security(api_key_header),
        db: Session = Depends(get_db)
):
    if not api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device API Key missing")

    hashed_key = get_api_key_hash(api_key)
    device = db.query(DeviceCredential).filter(
        DeviceCredential.api_key_hash == hashed_key,
        DeviceCredential.key_type == DeviceKeyType.DEVICE
    ).first()

    if not device or not device.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or inactive Device API Key")

    return device


async def verify_consumer_api_key(
        api_key: str = Security(consumer_api_key_header),
        db: Session = Depends(get_db)
):
    if not api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Consumer API Key missing")

    hashed_key = get_api_key_hash(api_key)
    consumer = db.query(DeviceCredential).filter(
        DeviceCredential.api_key_hash == hashed_key,
        DeviceCredential.key_type == DeviceKeyType.CONSUMER
    ).first()

    if not consumer or not consumer.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or inactive Consumer API Key")

    return consumer