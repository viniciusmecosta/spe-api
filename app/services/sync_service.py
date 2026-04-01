import os
import requests
from fastapi import UploadFile, HTTPException

from app.core.config import settings
from app.database.session import engine
from app.services.backup_service import backup_service


class SyncService:
    def receive_database(self, file: UploadFile):
        if settings.OPERATION_MODE != "CONSUMIDOR":
            raise HTTPException(status_code=403, detail="Apenas o Consumidor pode receber o banco de dados.")

        temp_path = "spe_temp.db"
        db_path = "spe.db"

        try:
            with open(temp_path, "wb") as buffer:
                buffer.write(file.file.read())

            engine.dispose()
            os.replace(temp_path, db_path)
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
            return

        try:
            url = f"{settings.CONSUMER_SERVER_URL.rstrip('/')}{settings.API_V1_STR}/sync/database"
            headers = {"X-CONSUMER-API-KEY": settings.CONSUMER_API_KEY}
            with open(backup_path, "rb") as f:
                files = {"file": ("spe.db", f, "application/octet-stream")}
                response = requests.post(url, headers=headers, files=files, timeout=60)
                response.raise_for_status()
        except Exception:
            pass
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)


sync_service = SyncService()