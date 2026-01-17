import logging
import pytz
from cachetools import TTLCache
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import Optional, Tuple

from app.core.config import settings
from app.domain.models import UserBiometric, TimeRecord
from app.schemas.mqtt import PunchPayload

logger = logging.getLogger(__name__)

# Cache para idempotência: armazena request_ids por 5 minutos
idempotency_cache = TTLCache(maxsize=1000, ttl=300)


class PunchService:
    def process_biometric_punch(self, db: Session, payload: PunchPayload) -> Tuple[bool, str, Optional[TimeRecord]]:
        """
        Processa o registro de ponto biométrico vindo do MQTT.
        Retorna: (sucesso: bool, mensagem: str, registro: TimeRecord | None)
        """
        # 1. Verificação de Idempotência
        if payload.request_id in idempotency_cache:
            logger.info(f"Request duplicado ignorado: {payload.request_id}")
            return False, "Duplicated request", None

        idempotency_cache[payload.request_id] = True

        # 2. Busca Biometria
        biometric = db.query(UserBiometric).filter(UserBiometric.sensor_index == payload.sensor_index).first()
        if not biometric:
            logger.error(f"Biometria não encontrada para sensor_index: {payload.sensor_index}")
            return False, "Biometria não cadastrada", None

        user = biometric.user
        if not user or not user.is_active:
            return False, "Usuário inativo ou não encontrado", None

        # 3. Determina Tipo de Registro (Entrada/Saída)
        # Busca o último registro deste usuário
        last_record = db.query(TimeRecord) \
            .filter(TimeRecord.user_id == user.id) \
            .order_by(desc(TimeRecord.timestamp)) \
            .first()

        new_type = "entry"
        if last_record and last_record.type == "entry":
            new_type = "exit"

        # 4. Converte Timestamp e Cria Registro
        tz = pytz.timezone(settings.TIMEZONE)
        # O dispositivo manda UTC/Unix, convertemos para timezone local
        record_time = datetime.fromtimestamp(payload.timestamp_device, tz=tz)

        new_record = TimeRecord(
            user_id=user.id,
            timestamp=record_time,
            type=new_type,
            biometric_id=biometric.id,
            is_manual=False
        )

        try:
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            logger.info(f"Ponto registrado: {user.full_name} - {new_type} às {record_time}")
            return True, "Sucesso", new_record
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao salvar ponto: {e}")
            return False, "Erro de banco de dados", None


punch_service = PunchService()
