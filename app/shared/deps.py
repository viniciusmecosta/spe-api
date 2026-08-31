import inspect
from collections.abc import Generator
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.security import get_api_key_hash
from app.database.session import (
    SessionLocal,
    get_async_db,
)
from app.features.auth.auth_schemas import TokenPayload
from app.features.devices.device_models import DeviceCredential
from app.features.users.user_models import User
from app.shared.enums import DeviceKeyType, UserRole

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


async def get_current_user(
        db: Annotated[Any, Depends(get_async_db)],
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
            detail="Não foi possível validar as credenciais.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not token_data.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = (
        select(User)
        .options(selectinload(User.current_schedules_rel), selectinload(User.biometrics))
        .where(User.id == int(str(token_data.sub)))
    )
    if hasattr(db, "scalars"):
        res = db.scalars(stmt)
        if inspect.isawaitable(res):
            res = await res
        user = res.first() if hasattr(res, "first") else None
    else:
        user = db.query(User).options(selectinload(User.current_schedules_rel), selectinload(User.biometrics)).filter(
            User.id == int(str(token_data.sub))).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user


def get_current_active_user(
        current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Usuário inativo.")
    return current_user


def get_current_manager(
        current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer privilégios de Gerente ou Mantenedor."
        )
    return current_user


def get_current_maintainer(
        current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role != UserRole.MAINTAINER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Requer privilégios de Mantenedor."
        )
    return current_user


async def verify_device_api_key(
        request: Request,
        api_key: Annotated[str | None, Security(api_key_header)],
        db: Annotated[Any, Depends(get_async_db)],
) -> DeviceCredential:
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave de API do dispositivo ausente.")

    hashed_key = get_api_key_hash(api_key)
    stmt = select(DeviceCredential).where(
        DeviceCredential.api_key_hash == hashed_key,
        DeviceCredential.key_type == DeviceKeyType.DEVICE,
    )
    if hasattr(db, "scalars"):
        res = db.scalars(stmt)
        if inspect.isawaitable(res):
            res = await res
        device = res.first() if hasattr(res, "first") else None
    else:
        device = db.query(DeviceCredential).filter(
            DeviceCredential.api_key_hash == hashed_key,
            DeviceCredential.key_type == DeviceKeyType.DEVICE,
        ).first()

    if not device or not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API do dispositivo inválida ou inativa.",
        )

    request.state.device_name = device.name
    return device


async def verify_consumer_api_key(
    request: Request,
    api_key: Annotated[str | None, Security(consumer_api_key_header)],
        db: Annotated[Any, Depends(get_async_db)],
) -> DeviceCredential:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API de integração ausente.",
        )

    hashed_key = get_api_key_hash(api_key)
    stmt = select(DeviceCredential).where(
        DeviceCredential.api_key_hash == hashed_key,
        DeviceCredential.key_type == DeviceKeyType.CONSUMER,
    )
    if hasattr(db, "scalars"):
        res = db.scalars(stmt)
        if inspect.isawaitable(res):
            res = await res
        consumer = res.first() if hasattr(res, "first") else None
    else:
        consumer = db.query(DeviceCredential).filter(
            DeviceCredential.api_key_hash == hashed_key,
            DeviceCredential.key_type == DeviceKeyType.CONSUMER,
        ).first()

    if not consumer or not consumer.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API de integração inválida ou inativa.",
        )

    request.state.device_name = consumer.name
    return consumer
