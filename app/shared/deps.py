import inspect
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Query, Request, Security, status
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
from app.features.auth.auth_models import RefreshToken
from app.features.auth.auth_schemas import TokenPayload
from app.features.devices.device_models import DeviceCredential
from app.features.users.user_models import User
from app.shared.enums import DeviceKeyType, UserRole

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)

api_key_header = APIKeyHeader(name="X-API-KEY", scheme_name="DeviceApiKey", auto_error=False)
SESSION_ENDED_DETAIL = "Sessão encerrada. Entre novamente."


def get_db() -> Generator[Session, None, None]:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


async def _fetch_user_by_id(db: Any, user_id: int) -> User | None:
    stmt = (
        select(User)
        .options(selectinload(User.current_schedules_rel), selectinload(User.biometrics))
        .where(User.id == user_id)
    )
    if hasattr(db, "scalars"):
        res = db.scalars(stmt)
        if inspect.isawaitable(res):
            res = await res
        return res.first() if hasattr(res, "first") else None
    return (
        db.query(User)
        .options(selectinload(User.current_schedules_rel), selectinload(User.biometrics))
        .filter(User.id == user_id)
        .first()
    )


async def _validate_user_session(db: Any, user: User, token_data: TokenPayload) -> None:
    if token_data.ver != (user.auth_version or 0):
        raise HTTPException(
            status_code=401,
            detail=SESSION_ENDED_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if token_data.purpose == "password_change" and user.password_change_required is not True:
        raise HTTPException(status_code=401, detail=SESSION_ENDED_DETAIL)
    if token_data.sid:
        valid_session = await db.scalar(
            select(RefreshToken.id)
            .where(
                RefreshToken.family_id == token_data.sid,
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.used_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .limit(1)
        )
        if not valid_session:
            raise HTTPException(status_code=401, detail=SESSION_ENDED_DETAIL)


async def get_password_change_user(
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

    if not token_data.sub or token_data.purpose not in ("access", "password_change"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await _fetch_user_by_id(db, int(str(token_data.sub)))
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    await _validate_user_session(db, user, token_data)
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuário inativo.")
    return user


async def get_current_user(
    db: Annotated[Any, Depends(get_async_db)],
    token: Annotated[str, Depends(reusable_oauth2)],
) -> User:
    current_user = await get_password_change_user(db, token)
    if current_user.password_change_required is True:
        raise HTTPException(status_code=403, detail={
            "code": "password_change_required", "message": "Redefina sua senha para continuar.",
        })
    return current_user


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

    custom_name = None
    if hasattr(request, "headers") and hasattr(request.headers, "get"):
        header_val = request.headers.get("X-Device-Name")
        if isinstance(header_val, str) and header_val.strip():
            custom_name = header_val.strip()[:100]

    request.state.device_name = custom_name if custom_name else device.name
    return device


def parse_optional_employee_ids(
        employee_ids: Annotated[list[str] | None, Query(description="Lista de IDs de colaboradores")] = None,
) -> list[int] | None:
    if not employee_ids:
        return None
    cleaned: list[int] = []
    for item in employee_ids:
        for part in item.split(","):
            part = part.strip()
            if not part.isascii() or not part.isdigit() or len(part) > 10 or not 0 < int(part) <= 2**31 - 1:
                raise HTTPException(status_code=422, detail="Informe somente IDs positivos de colaboradores.")
            employee_id = int(part)
            if employee_id not in cleaned:
                cleaned.append(employee_id)
    return cleaned
