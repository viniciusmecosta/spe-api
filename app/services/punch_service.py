import logging
from datetime import datetime
from pytz import timezone
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.time_record_service import time_record_service

logger = logging.getLogger(__name__)


class PunchService:
    def process_biometric_punch(self, db: Session, sensor_index: int):
        """
        Processa a batida usando o horario do Servidor.
        """
        try:
            from app.domain.models.biometric import UserBiometric

            biometric = db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_index).first()

            if not biometric:
                logger.warning(f"Batida recebida de index desconhecido: {sensor_index}")
                return False, "Nao Cadastrado", None

            user = biometric.user

            if not user.is_active:
                return False, "Bloqueado", None

            tz = timezone(settings.TIMEZONE)
            server_time = datetime.now(tz)

            new_record = time_record_service.create_punch(
                db,
                user_id=user.id,
                timestamp=server_time
            )

            return True, "Ponto Registrado", new_record

        except Exception as e:
            logger.error(f"Erro ao processar punch: {e}")
            return False, "Erro Interno", None


punch_service = PunchService()