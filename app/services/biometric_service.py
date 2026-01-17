import logging
import asyncio
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.domain.models import UserBiometric
from app.schemas.mqtt import BiometricSyncData, BiometricSyncAck
from app.core.mqtt import mqtt

logger = logging.getLogger(__name__)


class BiometricService:
    async def start_restore_process(self, db: Session):
        """
        Envia todas as biometrias cadastradas para o ESP32 via MQTT.
        """
        biometrics = db.query(UserBiometric).all()
        logger.info(f"Iniciando restore de {len(biometrics)} biometrias.")

        for bio in biometrics:
            payload = BiometricSyncData(
                biometric_id=bio.id,
                template_data=bio.template_data,
                user_id=bio.user_id
            )

            # Envia para o tópico de dados
            mqtt.publish("mh7/admin/sync/data", payload.model_dump_json())

            # Pequeno delay para evitar inundar o buffer do ESP32 (opcional, mas recomendado)
            await asyncio.sleep(0.1)

    def process_sync_ack(self, db: Session, ack: BiometricSyncAck):
        """
        Atualiza o sensor_index no banco baseado na confirmação do ESP32.
        """
        if not ack.success:
            logger.error(f"Erro ao gravar biometria ID {ack.biometric_id} no sensor: {ack.error}")
            return

        biometric = db.query(UserBiometric).filter(UserBiometric.id == ack.biometric_id).first()
        if not biometric:
            logger.warning(f"Biometria ID {ack.biometric_id} não encontrada para atualização.")
            return

        if biometric.sensor_index != ack.sensor_index:
            logger.info(
                f"Atualizando index da biometria {biometric.id}: {biometric.sensor_index} -> {ack.sensor_index}")

            # Verifica se já existe alguém com esse index (colisão rara em restore limpo, mas possível)
            existing = db.query(UserBiometric).filter(UserBiometric.sensor_index == ack.sensor_index).first()
            if existing and existing.id != biometric.id:
                # Em caso de colisão, removemos o index do registro antigo para liberar
                # (Assumindo que o restore atual é a verdade absoluta do sensor)
                logger.warning(
                    f"Conflito de index {ack.sensor_index} com biometria {existing.id}. Liberando index antigo.")
                existing.sensor_index = -1 * existing.id  # Valor temporário negativo para evitar erro Unique
                db.add(existing)
                db.flush()

            biometric.sensor_index = ack.sensor_index
            try:
                db.add(biometric)
                db.commit()
            except IntegrityError as e:
                db.rollback()
                logger.error(f"Erro de integridade ao atualizar index: {e}")
        else:
            logger.debug(f"Biometria {biometric.id} confirmada no index {ack.sensor_index} (sem alteração).")


biometric_service = BiometricService()