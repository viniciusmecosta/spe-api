import logging
import json
from pydantic import ValidationError
from app.core.mqtt import mqtt
from app.schemas.mqtt import PunchPayload
from app.services.punch_service import punch_service
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


@mqtt.subscribe("mh7/ponto/punch")
async def handle_punch(client, topic, payload, qos, properties):
    logger.info(f"Recebido payload em {topic}")

    try:
        data = json.loads(payload.decode())
        punch_data = PunchPayload(**data)

        db = SessionLocal()
        try:
            success, message, record = punch_service.process_biometric_punch(db, punch_data)

            if success and record:

                logger.info(f"Processamento concluído para {record.user.full_name}")
            else:
                logger.warning(f"Falha no processamento: {message}")

        finally:
            db.close()

    except ValidationError as e:
        logger.error(f"Payload inválido: {e}")
    except json.JSONDecodeError:
        logger.error("Erro ao decodificar JSON do MQTT")
    except Exception as e:
        logger.error(f"Erro inesperado no handler MQTT: {e}")