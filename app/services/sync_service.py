import logging
import os
import sqlite3

import requests
from fastapi import UploadFile, HTTPException

from app.core.config import settings
from app.database.session import engine, SessionLocal
from app.services.audit_service import audit_service
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
        except Exception:
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
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(status_code=500, detail=str(e))

        return True

    def send_database_to_consumer(self):
        if settings.OPERATION_MODE != "EXPORTADOR":
            return
        if not settings.CONSUMER_SERVER_URL or not settings.CONSUMER_API_KEY:
            return

        backup_path = backup_service._create_safe_backup("spe.db")
        if not backup_path:
            logger.error("Falha ao criar backup local para sincronizacao.")
            return

        db = SessionLocal()
        try:
            url = f"{settings.CONSUMER_SERVER_URL.rstrip('/')}{settings.API_V1_STR}/sync/database"
            headers = {"X-CONSUMER-API-KEY": settings.CONSUMER_API_KEY}
            with open(backup_path, "rb") as f:
                files = {"file": ("spe.db", f, "application/octet-stream")}
                response = requests.post(url, headers=headers, files=files, timeout=60)
                response.raise_for_status()

            logger.info("Sincronizacao remota realizada com sucesso.")
            audit_service.log(
                db=db,
                action="REMOTE_SYNC_SUCCESS",
                entity="SYSTEM",
                actor_name="Sistema",
                details="Sincronizacao de banco de dados com o consumidor realizada com sucesso."
            )

        except Exception as e:
            error_msg = f"Erro na sincronizacao remota: {str(e)}"
            logger.error(error_msg)
            audit_service.log(
                db=db,
                action="REMOTE_SYNC_ERROR",
                entity="SYSTEM",
                actor_name="Sistema",
                details=error_msg
            )
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            db.close()


sync_service = SyncService()
