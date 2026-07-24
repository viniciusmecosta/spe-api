import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackupService:
    def __init__(self):
        self._backup_lock = threading.Lock()

    def create_safe_backup(self) -> str | None:
        with self._backup_lock:
            try:
                tz = ZoneInfo(settings.TIMEZONE)
                timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
                unique_id = uuid.uuid4().hex[:8]
                backup_filename = f"temp_backup_{timestamp}_{unique_id}.db"

                src_conn = sqlite3.connect(settings.DATABASE_PATH)
                dst_conn = sqlite3.connect(backup_filename)

                src_conn.backup(dst_conn, pages=100, sleep=0.05)

                dst_conn.close()
                src_conn.close()

                return backup_filename
            except sqlite3.Error as e:
                logger.exception(f"Erro backup SQLite: {e}")
                return None


backup_service = BackupService()
