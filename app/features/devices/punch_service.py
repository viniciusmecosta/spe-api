import logging
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.database.session import get_async_db
from app.features.devices.device_models import UserBiometric
from app.features.devices.device_repository import AsyncBiometricRepository, async_biometric_repository
from app.features.system.audit_service import audit_service
from app.features.time_records.time_record_service import time_record_service
from app.shared.trusted_time_service import trusted_time_service

logger = logging.getLogger(__name__)


class PunchService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(get_async_db)] = None,
            repo: Annotated[AsyncBiometricRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncBiometricRepository:
        return self._repo if self._repo is not None else async_biometric_repository

    @repo.setter
    def repo(self, value: AsyncBiometricRepository) -> None:
        self._repo = value

    def _extract_device_name(self, request: Request | None) -> str | None:
        if not request:
            return None
        if hasattr(request, "headers") and hasattr(request.headers, "get"):
            header_device = request.headers.get("X-Device-Name")
            if isinstance(header_device, str) and header_device.strip():
                return header_device.strip()[:100]
        if hasattr(request, "state"):
            return getattr(request.state, "device_name", None)
        return None

    async def _handle_ntp_fallback(
            self,
            session: AsyncSession,
            new_record: Any,
            user_id: int,
            request: Request | None,
    ) -> None:
        if request and hasattr(request, "state"):
            request.state.ntp_error = True

        new_record.edit_justification = "Registro feito com a hora local do servidor (Falha no NTP)."
        session.add(new_record)
        await session.commit()

        await audit_service.async_log_change(
            session,
            user_id,
            "NTP_FALLBACK",
            entity="TIME_RECORD",
            entity_id=new_record.id,
            new_data={"justification": new_record.edit_justification}
        )

    async def _load_record_with_user(self, session: AsyncSession, record: Any):
        stmt_record = (
            select(record.__class__)
            .options(joinedload(record.__class__.user))
            .where(record.__class__.id == record.id)
        )
        result = await session.scalars(stmt_record)
        return result.first()

    async def process_biometric_punch(self, db: AsyncSession | None = None, sensor_index: int = 0,
                                      ip_address: str | None = None,
                                request: Request | None = None):
        session = db if db is not None else self.db
        assert session is not None
        try:
            stmt = select(UserBiometric).options(selectinload(UserBiometric.user)).where(
                UserBiometric.sensor_index == sensor_index)
            res = await session.scalars(stmt)
            biometric = res.first()

            if not biometric:
                return False, "Nao Cadastrado", None

            user = biometric.user
            if not user.is_active:
                return False, "Bloqueado", None

            server_time, used_ntp = trusted_time_service.get_trusted_time()
            device_name = self._extract_device_name(request)

            new_record = time_record_service.create_punch(
                session,
                user_id=user.id,
                timestamp=server_time,
                ip_address=ip_address if ip_address else "0.0.0.0",
                biometric_id=biometric.id,
                platform="IOT",
                device_name=device_name,
            )
            if hasattr(new_record, "__await__"):
                new_record = await new_record

            if not used_ntp:
                await self._handle_ntp_fallback(session, new_record, user.id, request)

            loaded_record = await self._load_record_with_user(session, new_record)
            return True, "Ponto Registrado", loaded_record

        except (SQLAlchemyError, ValueError) as e:
            logger.exception(f"Erro ao processar punch: {e}")
            return False, "Erro Interno", None


punch_service = PunchService()
