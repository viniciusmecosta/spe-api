import logging
from typing import Annotated

from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.features.devices.device_repository import AsyncBiometricRepository, async_biometric_repository
from app.features.devices.device_schemas import (
    BuzzerNote,
    DeviceActions,
    FeedbackPayload,
    ManagerVerifyResponse,
    TimeResponsePayload,
)
from app.features.devices.punch_service import punch_service
from app.features.system.audit_service import audit_service
from app.features.time_records.time_record_service import time_record_service
from app.shared.enums import RecordType, UserRole
from app.shared.trusted_time_service import trusted_time_service
from app.utils.formatters import format_short_name

logger = logging.getLogger(__name__)


class DeviceService:
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

    async def process_punch(
            self,
            db: AsyncSession | None = None,
            sensor_index: int = 0,
            ip_address: str = "",
            request: Request | None = None,
            background_tasks: BackgroundTasks | None = None,
    ) -> FeedbackPayload:
        session = db if db is not None else self.db
        assert session is not None
        try:
            success, message, record = await punch_service.process_biometric_punch(
                session, sensor_index, ip_address, request=request
            )

            if success and record:
                if background_tasks:
                    await time_record_service.trigger_auto_print(session, record, background_tasks)

                if request is not None and hasattr(request, "state") and record.user and record.user.name:
                    request.state.attempted_user = record.user.name
                user_short_name = format_short_name(record.user.name) if record.user and record.user.name else "Usuario"
                time_formatted = record.record_datetime.strftime("%H:%M")
                type_label = "Entrada" if record.record_type == RecordType.ENTRY else "Saida"

                return FeedbackPayload(
                    line1=user_short_name[:16],
                    line2=time_formatted,
                    line3=type_label,
                    led="green",
                    actions=DeviceActions(
                        buzzer_melody=[
                            BuzzerNote(frequency=1500, duration_ms=150),
                            BuzzerNote(frequency=0, duration_ms=50),
                            BuzzerNote(frequency=2000, duration_ms=300),
                        ]
                    ),
                )

            return FeedbackPayload(
                line1="Erro",
                line2=message[:16] if message else "",
                line3="",
                led="red",
                actions=DeviceActions(
                    buzzer_melody=[
                        BuzzerNote(frequency=250, duration_ms=300),
                        BuzzerNote(frequency=0, duration_ms=80),
                        BuzzerNote(frequency=250, duration_ms=600),
                    ]
                ),
            )
        except Exception:
            logger.exception("Erro interno ao processar ponto no dispositivo")
            return FeedbackPayload(
                line1="Erro Interno",
                line2="Contate Admin",
                line3="",
                led="red",
                actions=DeviceActions(
                    buzzer_melody=[
                        BuzzerNote(frequency=250, duration_ms=300),
                        BuzzerNote(frequency=0, duration_ms=80),
                        BuzzerNote(frequency=250, duration_ms=600),
                    ]
                ),
            )

    def get_device_time(self) -> TimeResponsePayload:
        trusted_now, _ = trusted_time_service.get_trusted_time()
        return TimeResponsePayload(
            unix=int(trusted_now.timestamp()),
            formatted=trusted_now.strftime("%d/%m/%Y %H:%M:%S"),
        )

    async def verify_manager_access(
            self,
            db: AsyncSession | None = None,
            sensor_index: int = 0,
            device_id: int = 0,
    ) -> ManagerVerifyResponse:
        session = db if db is not None else self.db
        assert session is not None
        managers_with_bio = await self.repo.get_manager_with_biometric(session)

        if not managers_with_bio:
            await audit_service.async_log_change(
                session,
                None,
                "VERIFY_MANAGER",
                entity="DEVICE",
                entity_id=device_id,
                new_data={"sensor_index": sensor_index, "status": "allowed", "reason": "no_managers"},
            )
            return ManagerVerifyResponse(
                is_allowed=True,
                message="Nenhum gestor cadastrado. Acesso liberado.",
            )

        biometric = await self.repo.get_by_sensor_index(session, sensor_index)
        if not biometric:
            await audit_service.async_log_change(
                session,
                None,
                "VERIFY_MANAGER",
                entity="DEVICE",
                entity_id=device_id,
                new_data={"sensor_index": sensor_index, "status": "denied", "reason": "biometric_not_found"},
            )
            return ManagerVerifyResponse(
                is_allowed=False,
                message="Biometria não encontrada.",
            )

        if biometric.user.role in [UserRole.MANAGER, UserRole.MAINTAINER] and biometric.user.is_active:
            await audit_service.async_log_change(
                session,
                biometric.user.id,
                "VERIFY_MANAGER",
                entity="DEVICE",
                entity_id=device_id,
                new_data={"sensor_index": sensor_index, "status": "allowed"},
            )
            return ManagerVerifyResponse(
                is_allowed=True,
                message="Acesso autorizado.",
            )

        await audit_service.async_log_change(
            session,
            biometric.user.id,
            "VERIFY_MANAGER",
            entity="DEVICE",
            entity_id=device_id,
            new_data={"sensor_index": sensor_index, "status": "denied", "reason": "insufficient_permissions"},
        )
        return ManagerVerifyResponse(
            is_allowed=False,
            message="Acesso negado.",
        )


device_service = DeviceService()
