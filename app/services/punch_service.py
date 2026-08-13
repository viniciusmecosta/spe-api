import logging
from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.audit_service import audit_service
from app.services.time_record_service import time_record_service
from app.services.trusted_time_service import trusted_time_service

logger = logging.getLogger(__name__)

class PunchService:
    def process_biometric_punch(self, db: Session, sensor_index: int, ip_address: str | None = None,
                                request: Request | None = None):
        try:
            from app.domain.models.biometric import UserBiometric
            biometric = db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_index).first()

            if not biometric:
                return False, "Nao Cadastrado", None

            user = biometric.user
            if not user.is_active:
                return False, "Bloqueado", None

            server_time, used_ntp = trusted_time_service.get_trusted_time()

            new_record = time_record_service.create_punch(
                db,
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
                db.add(new_record)
                db.commit()
                db.refresh(new_record)

                audit_service.log(
                    db,
                    user_id=user.id,
                    action="NTP_FALLBACK",
                    entity="TIME_RECORD",
                    entity_id=new_record.id,
                    new_data={"justification": new_record.edit_justification}
                )

            return True, "Ponto Registrado", new_record

        except (SQLAlchemyError, ValueError) as e:
            logger.exception(f"Erro ao processar punch: {e}")
            return False, "Erro Interno", None

punch_service = PunchService()
