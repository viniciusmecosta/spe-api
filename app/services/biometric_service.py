import logging
import asyncio
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.domain.models import UserBiometric
from app.schemas.mqtt import BiometricSyncData, BiometricSyncAck, EnrollResultPayload
from app.core.mqtt import mqtt

logger = logging.getLogger(__name__)

class BiometricService:
    async def start_restore_process(self, db: Session):
        biometrics = db.query(UserBiometric).all()
        for bio in biometrics:
            payload = BiometricSyncData(
                biometric_id=bio.id,
                template_data=bio.template_data,
                user_id=bio.user_id
            )
            mqtt.publish("mh7/admin/sync/data", payload.model_dump_json())
            await asyncio.sleep(0.1)

    def process_sync_ack(self, db: Session, ack: BiometricSyncAck):
        if not ack.success:
            return

        biometric = db.query(UserBiometric).filter(UserBiometric.id == ack.biometric_id).first()
        if not biometric:
            return

        if biometric.sensor_index != ack.sensor_index:
            existing = db.query(UserBiometric).filter(UserBiometric.sensor_index == ack.sensor_index).first()
            if existing and existing.id != biometric.id:
                existing.sensor_index = -1 * existing.id
                db.add(existing)
                db.flush()

            biometric.sensor_index = ack.sensor_index
            try:
                db.add(biometric)
                db.commit()
            except IntegrityError:
                db.rollback()

    def save_enrolled_biometric(self, db: Session, payload: EnrollResultPayload):
        if not payload.success:
            return False, "Enrollment failed on device"

        existing_bio = db.query(UserBiometric).filter(UserBiometric.sensor_index == payload.sensor_index).first()
        if existing_bio:
            db.delete(existing_bio)
            db.flush()

        new_bio = UserBiometric(
            user_id=payload.user_id,
            sensor_index=payload.sensor_index,
            template_data=payload.template_data,
            label=f"Enroll via Device"
        )
        try:
            db.add(new_bio)
            db.commit()
            return True, "Biometric saved"
        except Exception as e:
            db.rollback()
            return False, str(e)

biometric_service = BiometricService()