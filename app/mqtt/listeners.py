import json
import logging
import pytz
from datetime import datetime

from app.core.config import settings
from app.core.mqtt import mqtt
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType
from app.schemas.mqtt import (
    PunchPayload, FeedbackPayload, DeviceActions, TimeResponsePayload,
    BiometricSyncAck, EnrollResultPayload
)
from app.services.biometric_service import biometric_service
from app.services.punch_service import punch_service

logger = logging.getLogger(__name__)


@mqtt.subscribe("mh7/ponto/punch", qos=2)
async def handle_punch(client, topic, payload, qos, properties):
    """
    Recebe batida de ponto do ESP32.
    """
    try:
        data = json.loads(payload.decode())
        punch_data = PunchPayload(**data)
        db = SessionLocal()
        try:
            success, message, record = punch_service.process_biometric_punch(db, punch_data)
        finally:
            db.close()

        if success and record:
            user_first_name = record.user.name.split()[0] if record.user.name else "Usuario"
            time_formatted = record.record_datetime.strftime('%H:%M')
            type_label = "Entrada" if record.record_type == RecordType.ENTRY else "Saida"

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
        mqtt.publish("mh7/ponto/response", response.model_dump_json(), qos=2)
    except Exception as e:
        logger.error(f"Erro no handler de punch: {e}")


@mqtt.subscribe("mh7/global/time/req", qos=2)
async def handle_time_sync(client, topic, payload, qos, properties):
    """
    Responde com a hora atual para o ESP32 sincronizar o RTC.
    """
    try:
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)
        response = TimeResponsePayload(unix=int(now.timestamp()), formatted=now.strftime("%d/%m/%Y %H:%M:%S"))
        mqtt.publish("mh7/global/time/resp", response.model_dump_json(), qos=2)
    except Exception as e:
        logger.error(f"Erro sync time: {e}")


@mqtt.subscribe("mh7/admin/sync/start", qos=2)
async def handle_sync_start(client, topic, payload, qos, properties):
    """
    O ESP32 entrou em modo SYNC e pediu os dados.
    Envia todas as biometrias cadastradas uma por uma.
    """
    db = SessionLocal()
    try:
        await biometric_service.start_restore_process(db)
    except Exception as e:
        logger.error(f"Erro ao processar sync start: {e}")
    finally:
        db.close()


@mqtt.subscribe("mh7/admin/sync/ack", qos=2)
async def handle_sync_ack(client, topic, payload, qos, properties):
    """
    O ESP32 confirmou que salvou uma biometria enviada no Sync.
    """
    try:
        data = json.loads(payload.decode())
        ack_data = BiometricSyncAck(**data)
        db = SessionLocal()
        try:
            biometric_service.process_sync_ack(db, ack_data)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Erro ao processar sync ack: {e}")


@mqtt.subscribe("mh7/admin/enroll/result", qos=2)
async def handle_enroll_result(client, topic, payload, qos, properties):
    """
    Recebe o template biométrico capturado pelo ESP32 após comando remoto.
    """
    try:
        data = json.loads(payload.decode())
        result = EnrollResultPayload(**data)
        db = SessionLocal()

        feedback_response = None

        try:
            success, msg = biometric_service.save_enrolled_biometric(db, result)

            if success:
                feedback_response = FeedbackPayload(
                    request_id="enroll_result",
                    line1="Cadastro OK",
                    line2=f"ID: {result.sensor_index}",
                    actions=DeviceActions(
                        led_color="green", led_duration_ms=2000, buzzer_pattern=1, buzzer_duration_ms=500
                    )
                )
            else:
                feedback_response = FeedbackPayload(
                    request_id="enroll_result",
                    line1="Erro Cadastro",
                    line2=msg[:16],
                    actions=DeviceActions(
                        led_color="red", led_duration_ms=2000, buzzer_pattern=2, buzzer_duration_ms=1000
                    )
                )
        finally:
            db.close()

        if feedback_response:
            mqtt.publish("mh7/ponto/response", feedback_response.model_dump_json(), qos=2)

    except Exception as e:
        logger.error(f"Erro ao processar enroll result: {e}")
