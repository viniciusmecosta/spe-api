import logging
from datetime import datetime
from sqlalchemy.orm import Session

from app.schemas.mqtt import PunchPayload
from app.services.time_record_service import time_record_service

logger = logging.getLogger(__name__)


class PunchService:
    def process_biometric_punch(self, db: Session, punch_data: PunchPayload):
        """
        Processa a batida de ponto recebida do ESP32.
        Retorna (Sucesso, Mensagem, Registro)
        """
        try:
            from app.domain.models.biometric import UserBiometric

            biometric = db.query(UserBiometric).filter(UserBiometric.sensor_index == punch_data.sensor_index).first()

            if not biometric:
                logger.warning(f"Batida recebida de index desconhecido: {punch_data.sensor_index}")
                return False, "Nao Cadastrado", None

            user = biometric.user

            if not user.is_active:
                return False, "Bloqueado", None

            new_record = time_record_service.create_punch(
                db,
                user_id=user.id,
                timestamp=datetime.fromtimestamp(punch_data.timestamp_device)
            )

            return True, "Ponto Registrado", new_record

        except Exception as e:
            logger.error(f"Erro ao processar punch: {e}")
            return False, "Erro Interno", None


punch_service = PunchService()
