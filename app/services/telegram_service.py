import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, date, time
from typing import Dict, List
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logger import get_log_path
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType
from app.domain.models.routine_log import RoutineLog
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User
from app.services.backup_service import backup_service

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID



    def send_text(self, text: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=payload, timeout=15)
            is_success = 200 <= response.status_code <= 299
            if not is_success:
                logger.error(f"Telegram API Error (Text): Status {response.status_code} - {response.text}")
            return is_success
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram send text error: {e}")
            return False

    def send_document(self, file_path: str, caption: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
            with open(file_path, "rb") as file:
                payload = {"chat_id": self.chat_id, "caption": caption}
                files = {"document": file}
                response = requests.post(url, data=payload, files=files, timeout=40)
            is_success = 200 <= response.status_code <= 299
            if not is_success:
                logger.error(f"Telegram API Error (Document): Status {response.status_code} - {response.text}")
            return is_success
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram send document error: {e}")
            return False

    def _format_name(self, full_name: str) -> str:
        parts = full_name.split()
        if len(parts) <= 1:
            return full_name
        first_name = parts[0]
        second_name = next((p for p in parts[1:] if len(p) > 3), parts[1])
        return f"{first_name} {second_name}"

    def generate_report_text(self, db: Session, start_date: date, end_date: date,
                              title_prefix: str = "Relatório Gerencial - Fechamento") -> str:
        try:
            fmt_start = start_date.strftime("%d/%m/%Y")
            fmt_end = end_date.strftime("%d/%m/%Y")

            if start_date == end_date:
                title_date = fmt_start
            else:
                title_date = f"{fmt_start} a {fmt_end}"

            text = f"<b>{title_prefix} {title_date}</b>\n\n"

            start_dt = datetime.combine(start_date, time.min)
            end_dt = datetime.combine(end_date, time.max)

            records = (
                db.query(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .filter(TimeRecord.record_datetime >= start_dt)
                .filter(TimeRecord.record_datetime <= end_dt)
                .filter(TimeRecord.is_ignored == False)
                .order_by(TimeRecord.record_datetime, User.name)
                .all()
            )

            if not records:
                text += "Sem registros de ponto no período."
                return text

            daily_activity: Dict[str, Dict[str, List[str]]] = {}
            for record, user in records:
                date_str = record.record_datetime.strftime("%d/%m/%Y")
                time_str = record.record_datetime.strftime("%H:%M")
                marker = "E:" if record.record_type == RecordType.ENTRY else "S:"

                fmt_name = self._format_name(user.name)

                if date_str not in daily_activity:
                    daily_activity[date_str] = {}

                if fmt_name not in daily_activity[date_str]:
                    daily_activity[date_str][fmt_name] = []

                daily_activity[date_str][fmt_name].append(f"{marker} {time_str}")

            for d_str, users_data in daily_activity.items():
                if len(text) > settings.TELEGRAM_MAX_MESSAGE_LENGTH:
                    break

                text += f"<b>{d_str}</b>\n"
                for name, punches in users_data.items():
                    punches_str = " | ".join(punches)
                    text += f"{name} - {punches_str}\n"
                text += "\n"

            return text.strip()
        except Exception as e:
            logger.error(f"Telegram report generation error: {e}")
            return "Erro interno ao gerar relatório gerencial."




telegram_service = TelegramService()
