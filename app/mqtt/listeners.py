import logging
import json
from datetime import datetime
import pytz
from pydantic import ValidationError
from app.core.mqtt import mqtt
from app.core.config import settings
from app.schemas.mqtt import PunchPayload, FeedbackPayload, DeviceActions, TimeResponsePayload, BiometricSyncAck
from app.services.punch_service import punch_service
from app.services.biometric_service import biometric_service
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


# ... (Handlers anteriores: handle_punch, handle_time_sync mantidos) ...

@mqtt.subscribe("mh7/ponto/punch")
async def handle_punch(client, topic, payload, qos, properties):
    # (Código existente mantido)
    logger.info(f"Recebido payload em {topic}")
    try:
        data = json.loads(payload.decode())
        punch_data = PunchPayload(**data)
        db = SessionLocal()
        try:
            success, message, record = punch_service.process_biometric_punch(db, punch_data)
        finally:
            db.close()

        if success and record:
            user_first_name = record.user.full_name.split()[0] if record.user.full_name else "Usuario"
            time_formatted = record.timestamp.strftime('%H:%M')
            type_label = "Entrada" if record.type == "entry" else "Saida"
            response = FeedbackPayload(
                request_id=punch_data.request_id,
                line1=f"Ola, {user_first_name[:11]}",
                line2=f"{type_label} {time_formatted}",
                actions=DeviceActions(
                    led_color="green", led_duration_ms=3000, buzzer_pattern=1, buzzer_duration_ms=500
                )
            )
        else:
            response = FeedbackPayload(
                request_id=punch_data.request_id,
                line1="Erro",
                line2=message[:16],
                actions=DeviceActions(
                    led_color="red", led_duration_ms=3000, buzzer_pattern=2, buzzer_duration_ms=1000
                )
            )
        mqtt.publish("mh7/ponto/response", response.model_dump_json())
    except Exception as e:
        logger.error(f"Erro no handler de punch: {e}")


@mqtt.subscribe("mh7/global/time/req")
async def handle_time_sync(client, topic, payload, qos, properties):
    # (Código existente mantido)
    try:
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)
        response = TimeResponsePayload(unix=int(now.timestamp()), formatted=now.strftime("%d/%m/%Y %H:%M:%S"))
        mqtt.publish("mh7/global/time/resp", response.model_dump_json())
    except Exception as e:
        logger.error(f"Erro sync time: {e}")


# --- Novos Handlers de Restore ---

@mqtt.subscribe("mh7/admin/sync/start")
async def handle_sync_start(client, topic, payload, qos, properties):
    """Inicia o processo de envio de todas as biometrias para o ESP."""
    logger.info("Solicitação de restore de biometrias recebida.")
    db = SessionLocal()
    try:
        await biometric_service.start_restore_process(db)
    except Exception as e:
        logger.error(f"Erro ao processar sync start: {e}")
    finally:
        db.close()


@mqtt.subscribe("mh7/admin/sync/ack")
async def handle_sync_ack(client, topic, payload, qos, properties):
    """Processa a confirmação de gravação do ESP e atualiza o index."""
    try:
        data = json.loads(payload.decode())
        ack_data = BiometricSyncAck(**data)

        db = SessionLocal()
        try:
            biometric_service.process_sync_ack(db, ack_data)
        finally:
            db.close()
    except ValidationError as e:
        logger.error(f"Payload de ACK inválido: {e}")
    except Exception as e:
        logger.error(f"Erro ao processar sync ack: {e}")