import logging
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from fastapi import UploadFile, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.database.session import engine, get_db_session
from app.domain.models.routine_log import RoutineLog
from app.repositories.time_record_repository import time_record_repository
from app.services.backup_service import backup_service

logger = logging.getLogger(__name__)


class SyncService:
    def _check_sqlite_integrity(self, db_path: str) -> bool:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            conn.close()
            return result and result[0] == "ok"
        except sqlite3.Error:
            return False

    def receive_database(self, file: UploadFile):
        if settings.OPERATION_MODE != "CONSUMIDOR":
            raise HTTPException(status_code=403, detail="Apenas o Consumidor pode receber o banco de dados.")

        temp_path = "spe_temp.db"
        db_path = "spe.db"
        wal_path = "spe.db-wal"
        shm_path = "spe.db-shm"

        try:
            with open(temp_path, "wb") as buffer:
                buffer.write(file.file.read())

            if not self._check_sqlite_integrity(temp_path):
                os.remove(temp_path)
                raise HTTPException(status_code=400, detail="Arquivo de banco de dados corrompido ou invalido.")

            engine.dispose()
            os.replace(temp_path, db_path)

            if os.path.exists(wal_path):
                os.remove(wal_path)
            if os.path.exists(shm_path):
                os.remove(shm_path)

        except (OSError, sqlite3.Error) as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            logger.error(f'Sincronização - "Receber banco de dados" Error: {e}')
            raise HTTPException(status_code=500, detail=str(e))

        return True

    def send_database_to_consumer(self):
        if settings.OPERATION_MODE != "EXPORTADOR":
            return
        if not settings.CONSUMER_SERVER_URL or not settings.CONSUMER_API_KEY:
            return

        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)

        try:
            with get_db_session() as db_read:
                current_hour_start = now.replace(minute=0, second=0, microsecond=0)
                exists = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "REMOTE_SYNC_DATABASE",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.execution_time >= current_hour_start
                ).first()
                if exists:
                    return
        except SQLAlchemyError:
            return

        backup_path = backup_service.create_safe_backup()
        if not backup_path:
            logger.error('Sincronização - "Enviar banco de dados" Error ao gerar backup')
            return

        try:
            url = f"{settings.CONSUMER_SERVER_URL.rstrip('/')}{settings.API_V1_STR}/sync/database"
            headers = {"X-CONSUMER-API-KEY": settings.CONSUMER_API_KEY}
            with open(backup_path, "rb") as f:
                files = {"file": ("spe.db", f, "application/octet-stream")}
                response = requests.post(url, headers=headers, files=files, timeout=60)
                response.raise_for_status()

            with get_db_session() as db_write:
                log_entry = RoutineLog(
                    routine_type="REMOTE_SYNC_DATABASE",
                    status="SUCCESS"
                )
                db_write.add(log_entry)
        except requests.RequestException as e:
            logger.error(f'Sincronização - "Enviar banco de dados" HTTP Error: {e}')
            try:
                with get_db_session() as db_err:
                    log_error = RoutineLog(routine_type="REMOTE_SYNC_DATABASE", status="FAILED")
                    db_err.add(log_error)
            except SQLAlchemyError:
                pass
        except SQLAlchemyError as e:
            logger.error(f'Sincronização - "Enviar banco de dados" DB Error: {e}')
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)

    def check_and_sync_all(self):
        if settings.OPERATION_MODE != "EXPORTADOR":
            return

        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)

        try:
            with get_db_session() as db_read:
                current_hour_start = now.replace(minute=0, second=0, microsecond=0)
                exists = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "SYNC_TIME_RECORDS",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.execution_time >= current_hour_start
                ).first()

                if exists:
                    return

                records = time_record_repository.get_unsynced(db_read)
                if not records:
                    log_entry = RoutineLog(
                        routine_type="SYNC_TIME_RECORDS",
                        status="SUCCESS"
                    )
                    db_read.add(log_entry)
                    return

                records_data = [{"id": r.id, "user_id": r.user_id, "timestamp": r.record_datetime.isoformat()} for r in
                                records]
        except SQLAlchemyError:
            return

        try:
            for rec in records_data:
                payload = {"user_id": rec["user_id"], "timestamp": rec["timestamp"]}
                res = requests.post(f"{settings.CONSUMER_SERVER_URL}/sync", json=payload, timeout=10)
                if res.status_code == 200:
                    with get_db_session() as db_mark:
                        time_record_repository.mark_as_synced(db_mark, rec["id"])

            with get_db_session() as db_write:
                log_entry = RoutineLog(
                    routine_type="SYNC_TIME_RECORDS",
                    status="SUCCESS"
                )
                db_write.add(log_entry)
        except (requests.RequestException, SQLAlchemyError) as e:
            logger.error(f'Sincronização - "Registros de ponto" Error: {e}')

sync_service = SyncService()
