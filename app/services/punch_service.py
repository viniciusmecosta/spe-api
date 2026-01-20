import logging
from datetime import datetime
from typing import Optional, Tuple

import pytz
from cachetools import TTLCache
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models import UserBiometric, TimeRecord
from app.domain.models.enums import RecordType
from app.schemas.mqtt import PunchPayload

logger = logging.getLogger(__name__)

idempotency_cache = TTLCache(maxsize=1000, ttl=300)


class PunchService:
    def process_biometric_punch(self, db: Session, payload: PunchPayload) -> Tuple[bool, str, Optional[TimeRecord]]:
        if payload.request_id in idempotency_cache:
            logger.info(f"Request duplicado ignorado: {payload.request_id}")
            return False, "Duplicated request", None

        idempotency_cache[payload.request_id] = True

        biometric = db.query(UserBiometric).filter(UserBiometric.sensor_index == payload.sensor_index).first()
        if not biometric:
            logger.error(f"Biometria não encontrada para sensor_index: {payload.sensor_index}")
            return False, "Biometria não cadastrada", None

        user = biometric.user
        if not user or not user.is_active:
            return False, "Usuário inativo ou não encontrado", None

        last_record = db.query(TimeRecord) \
            .filter(TimeRecord.user_id == user.id) \
            .order_by(desc(TimeRecord.record_datetime)) \
            .first()

        new_type = RecordType.ENTRY
        if last_record and last_record.record_type == RecordType.ENTRY:
            new_type = RecordType.EXIT

        tz = pytz.timezone(settings.TIMEZONE)
        record_time = datetime.fromtimestamp(payload.timestamp_device, tz=tz)

        new_record = TimeRecord(
            user_id=user.id,
            record_datetime=record_time,
            record_type=new_type,
            biometric_id=biometric.id,
            is_manual=False
        )

        try:
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            logger.info(f"Ponto registrado: {user.name} - {new_type} às {record_time}")
            return True, "Sucesso", new_record
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao salvar ponto: {e}")
            return False, "Erro de banco de dados", None


punch_service = PunchService()
