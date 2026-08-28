import logging
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

            new_record = time_record_service.create_punch(
                session,
                user_id=user.id,
                timestamp=server_time,
                ip_address=ip_address if ip_address else "0.0.0.0",
                biometric_id=biometric.id,
                platform="IOT"
            )
            if hasattr(new_record, "__await__"):
                new_record = await new_record

            if not used_ntp:
                if request:
                    request.state.ntp_error = True

                new_record.edit_justification = "Registro feito com a hora local do servidor (Falha no NTP)."
                session.add(new_record)
                await session.commit()
                await session.refresh(new_record)

                await audit_service.async_log_change(
                    session,
                    user.id,
                    "NTP_FALLBACK",
                    entity="TIME_RECORD",
                    entity_id=new_record.id,
                    new_data={"justification": new_record.edit_justification}
                )

            return True, "Ponto Registrado", new_record

        except (SQLAlchemyError, ValueError) as e:
            logger.exception(f"Erro ao processar punch: {e}")
            return False, "Erro Interno", None


punch_service = PunchService()
