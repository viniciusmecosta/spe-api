import logging

from fastapi import BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.features.devices.device_repository import biometric_repository
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
    def process_punch(
            self,
            db: Session,
            sensor_index: int,
            ip_address: str,
            request: Request | None = None,
            background_tasks: BackgroundTasks | None = None,
    ) -> FeedbackPayload:
        try:
            success, message, record = punch_service.process_biometric_punch(
                db, sensor_index, ip_address, request=request
            )

            if success and record:
                if background_tasks:
                    time_record_service.trigger_auto_print(db, record, background_tasks)

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

    def verify_manager_access(
            self,
            db: Session,
            sensor_index: int,
            device_id: int,
    ) -> ManagerVerifyResponse:
        managers_with_bio = biometric_repository.get_manager_with_biometric(db)

        if not managers_with_bio:
            audit_service.log_change(
                db,
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

        biometric = biometric_repository.get_by_sensor_index(db, sensor_index)
        if not biometric:
            audit_service.log_change(
                db,
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
            audit_service.log_change(
                db,
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

        audit_service.log_change(
            db,
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
