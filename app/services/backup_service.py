import logging
import os
import smtplib
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, date, time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
from typing import Dict, List, Tuple, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logger import get_log_path
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType, UserRole
from app.domain.models.routine_log import RoutineLog
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User

logger = logging.getLogger(__name__)


class BackupService:
    def __init__(self):
        self._backup_lock = threading.Lock()

    def create_safe_backup(self) -> Optional[str]:
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
                logger.error(f"Erro backup SQLite: {e}")
                return None




backup_service = BackupService()
