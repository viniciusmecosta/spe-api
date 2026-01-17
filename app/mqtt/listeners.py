import logging
import json
from datetime import datetime
import pytz
from pydantic import ValidationError
from app.core.mqtt import mqtt
from app.core.config import settings
from app.schemas.mqtt import PunchPayload, FeedbackPayload, DeviceActions, TimeResponsePayload
from app.services.punch_service import punch_service
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


@mqtt.subscribe("mh7/ponto/punch")
async def handle_punch(client, topic, payload, qos, properties):
    logger.info(f"Recebido payload em {topic}")

    try:
        # 1. Decodifica Payload
        data = json.loads(payload.decode())
        punch_data = PunchPayload(**data)

        # 2. Processa Regra de Negócio
        db = SessionLocal()
        try:
            success, message, record = punch_service.process_biometric_punch(db, punch_data)
        finally:
            db.close()

        # 3. Constroi Feedback
        if success and record:
            # Lógica de Sucesso
            user_first_name = record.user.full_name.split()[0] if record.user.full_name else "Usuario"
            time_formatted = record.timestamp.strftime('%H:%M')
            type_label = "Entrada" if record.type == "entry" else "Saida"

            response = FeedbackPayload(
                request_id=punch_data.request_id,
                line1=f"Ola, {user_first_name[:11]}",  # Garante caber no display
                line2=f"{type_label} {time_formatted}",
                actions=DeviceActions(
                    led_color="green",
                    led_duration_ms=3000,
                    buzzer_pattern=1,
                    buzzer_duration_ms=500
                )
            )
        else:
            # Lógica de Erro (Biometria não encontrada, Duplicado, etc)
            logger.warning(f"Erro no processamento: {message}")
            response = FeedbackPayload(
                request_id=punch_data.request_id,
                line1="Erro",
                line2=message[:16],  # Trunca mensagem para o display
                actions=DeviceActions(
                    led_color="red",
                    led_duration_ms=3000,
                    buzzer_pattern=2,
                    buzzer_duration_ms=1000
                )
            )

        # 4. Envia Feedback ao ESP32
        mqtt.publish(
            "mh7/ponto/response",
            response.model_dump_json()
        )
        logger.info(f"Feedback enviado para request {punch_data.request_id}: {response.line1} / {response.line2}")

    except ValidationError as e:
        logger.error(f"Payload inválido: {e}")
    except json.JSONDecodeError:
        logger.error("Erro ao decodificar JSON do MQTT")
    except Exception as e:
        logger.error(f"Erro inesperado no handler MQTT: {e}")


@mqtt.subscribe("mh7/global/time/req")
async def handle_time_sync(client, topic, payload, qos, properties):
    """
    Responde à solicitação de sincronização de hora do ESP32.
    """
    logger.debug(f"Recebido pedido de sync de hora em {topic}")

    try:
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)

        response = TimeResponsePayload(
            unix=int(now.timestamp()),
            formatted=now.strftime("%d/%m/%Y %H:%M:%S")
        )

        mqtt.publish(
            "mh7/global/time/resp",
            response.model_dump_json()
        )
        logger.info(f"Hora enviada para ESP32: {response.formatted}")

    except Exception as e:
        logger.error(f"Erro ao processar sincronização de hora: {e}")