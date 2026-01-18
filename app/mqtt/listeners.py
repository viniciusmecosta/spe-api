import json
import logging
import pytz
from datetime import datetime
from pydantic import ValidationError

from app.core.config import settings
from app.core.mqtt import mqtt
from app.database.session import SessionLocal
from app.domain.models import UserBiometric
from app.domain.models.enums import UserRole
from app.repositories.user_repository import user_repository
from app.schemas.mqtt import (
    PunchPayload, FeedbackPayload, DeviceActions, TimeResponsePayload,
    BiometricSyncAck, AdminAuthRequest, AdminAuthResponse,
    EnrollResultPayload, UserListResponse, UserItem
)
from app.services.biometric_service import biometric_service
from app.services.punch_service import punch_service

logger = logging.getLogger(__name__)


@mqtt.subscribe("mh7/ponto/punch", qos=2)
async def handle_punch(client, topic, payload, qos, properties):
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
        mqtt.publish("mh7/ponto/response", response.model_dump_json(), qos=2)
    except Exception as e:
        logger.error(f"Erro no handler de punch: {e}")


@mqtt.subscribe("mh7/global/time/req", qos=2)
async def handle_time_sync(client, topic, payload, qos, properties):
    try:
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)
        response = TimeResponsePayload(unix=int(now.timestamp()), formatted=now.strftime("%d/%m/%Y %H:%M:%S"))
        mqtt.publish("mh7/global/time/resp", response.model_dump_json(), qos=2)
    except Exception as e:
        logger.error(f"Erro sync time: {e}")


@mqtt.subscribe("mh7/admin/sync/start", qos=2)
async def handle_sync_start(client, topic, payload, qos, properties):
    db = SessionLocal()
    try:
        await biometric_service.start_restore_process(db)
    except Exception as e:
        logger.error(f"Erro ao processar sync start: {e}")
    finally:
        db.close()


@mqtt.subscribe("mh7/admin/sync/ack", qos=2)
async def handle_sync_ack(client, topic, payload, qos, properties):
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


@mqtt.subscribe("mh7/admin/auth/req", qos=2)
async def handle_admin_auth(client, topic, payload, qos, properties):
    try:
        data = json.loads(payload.decode())
        auth_req = AdminAuthRequest(**data)

        db = SessionLocal()
        authorized = False
        user_name = "Desconhecido"
        try:
            biometric = db.query(UserBiometric).filter(UserBiometric.sensor_index == auth_req.sensor_index).first()
            if biometric and biometric.user:
                user = biometric.user
                user_name = user.name.split()[0] if user.name else "Usuario"
                if user.is_active and user.role in [UserRole.MANAGER, UserRole.MAINTAINER]:
                    authorized = True
        finally:
            db.close()

        response = AdminAuthResponse(
            request_id=auth_req.request_id,
            authorized=authorized,
            user_name=user_name
        )
        mqtt.publish("mh7/admin/auth/resp", response.model_dump_json(), qos=2)

    except Exception as e:
        logger.error(f"Erro ao processar auth admin: {e}")


@mqtt.subscribe("mh7/admin/enroll/result", qos=2)
async def handle_enroll_result(client, topic, payload, qos, properties):
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


@mqtt.subscribe("mh7/admin/users/req", qos=2)
async def handle_users_req(client, topic, payload, qos, properties):
    db = SessionLocal()
    try:
        users = user_repository.get_multi(db, limit=1000)
        active_users = [
            UserItem(id=u.id, name=u.name[:16])
            for u in users if u.is_active
        ]

        response = UserListResponse(users=active_users)
        mqtt.publish("mh7/admin/users/resp", response.model_dump_json(), qos=2)
    finally:
        db.close()