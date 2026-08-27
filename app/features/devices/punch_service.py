import logging
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.features.devices.device_models import UserBiometric
from app.features.system.audit_service import audit_service
from app.features.time_records.time_record_service import time_record_service
from app.shared import deps
from app.shared.trusted_time_service import trusted_time_service

logger = logging.getLogger(__name__)


class PunchService:
    def __init__(self, db: Annotated[Session, Depends(deps.get_db)] = None):
        self.db = db

    def process_biometric_punch(self, db: Session | None = None, sensor_index: int = 0, ip_address: str | None = None,
                                request: Request | None = None):
        session = db if db is not None else self.db
        assert session is not None
        try:
            biometric = session.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_index).first()

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

            if not used_ntp:
                if request:
                    request.state.ntp_error = True

                new_record.edit_justification = "Registro feito com a hora local do servidor (Falha no NTP)."
                session.add(new_record)
                session.commit()
                session.refresh(new_record)

                audit_service.log_change(
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
