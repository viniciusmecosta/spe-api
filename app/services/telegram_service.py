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

from app.core.config import settings
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType
from app.domain.models.routine_log import RoutineLog
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.db_path = "spe.db"
        self._hourly_lock = threading.Lock()
        self._daily_lock = threading.Lock()
        self._manual_backup_lock = threading.Lock()
        self._manual_report_lock = threading.Lock()

    def _create_safe_backup(self) -> str | None:
        if not os.path.exists(self.db_path):
            return None

        try:
            tz = ZoneInfo(settings.TIMEZONE)
            timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            backup_filename = f"temp_backup_{timestamp}_{unique_id}.db"

            src_conn = sqlite3.connect(self.db_path)
            dst_conn = sqlite3.connect(backup_filename)

            src_conn.backup(dst_conn, pages=100, sleep=0.05)

            dst_conn.close()
            src_conn.close()

            return backup_filename
        except Exception:
            return None

    def _send_text(self, text: str) -> bool:
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
        except Exception as e:
            logger.error(f"Telegram send text error: {e}")
            return False

    def _send_document(self, file_path: str, caption: str) -> bool:
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
        except Exception as e:
            logger.error(f"Telegram send document error: {e}")
            return False

    def _format_name(self, full_name: str) -> str:
        parts = full_name.split()
        if len(parts) <= 1:
            return full_name
        first_name = parts[0]
        second_name = next((p for p in parts[1:] if len(p) > 3), parts[1])
        return f"{first_name} {second_name}"

    def _generate_report_text(self, db: Session, start_date: date, end_date: date,
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
                if len(text) > 3900:
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

    def execute_hourly_backup(self):
        with self._hourly_lock:
            tz = ZoneInfo(settings.TIMEZONE)
            now = datetime.now(tz)
            now_local = now.replace(tzinfo=None)

            db_read = SessionLocal()
            try:
                current_hour_start_local = now_local.replace(minute=0, second=0, microsecond=0)

                exists = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "TELEGRAM_HOURLY_BACKUP",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.execution_time >= current_hour_start_local
                ).first()
                if exists:
                    return
            except Exception as e:
                logger.error(f"Erro ao verificar backup horário Telegram: {e}")
                return
            finally:
                db_read.close()

            backup_path = self._create_safe_backup()
            if not backup_path:
                logger.error('Backup - "Telegram horário" Error')
                return

            now_str = now_local.strftime('%H:%M')
            caption = f"[Backup Automático] - {now_str}"

            success = self._send_document(backup_path, caption)

            if os.path.exists(backup_path):
                os.remove(backup_path)

            db_write = SessionLocal()
            try:
                if success:
                    log_entry = RoutineLog(
                        routine_type="TELEGRAM_HOURLY_BACKUP",
                        status="SUCCESS",
                        execution_time=now_local
                    )
                    db_write.add(log_entry)
                    db_write.commit()
                    logger.info('Backup - "Telegram horário" OK')
                else:
                    logger.error('Backup - "Telegram horário" Error')
            except Exception as e:
                db_write.rollback()
                logger.error(f'Backup - "Telegram horário" DB Error: {e}')
            finally:
                db_write.close()

    def send_managerial_report(self):
        with self._daily_lock:
            tz = ZoneInfo(settings.TIMEZONE)
            now = datetime.now(tz)
            now_local = now.replace(tzinfo=None)
            today = now_local.date()
            yesterday = today - timedelta(days=1)

            if now_local.hour < 9:
                return

            db_read = SessionLocal()
            try:
                ran_today = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "TELEGRAM_DAILY_REPORT",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.target_date == yesterday
                ).first()

                if ran_today:
                    return

                last_success = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "TELEGRAM_DAILY_REPORT",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.target_date.isnot(None)
                ).order_by(desc(RoutineLog.target_date)).first()

                if last_success and last_success.target_date:
                    start_date = last_success.target_date + timedelta(days=1)
                else:
                    start_date = yesterday

                if start_date > yesterday:
                    start_date = yesterday

                report_text = self._generate_report_text(db_read, start_date, yesterday)
            except Exception as e:
                logger.error(f"Erro ao gerar report gerencial Telegram: {e}")
                return
            finally:
                db_read.close()

            text_success = self._send_text(report_text)

            current_log_date = start_date
            while current_log_date <= yesterday:
                log_filename = current_log_date.strftime("%d%m%Y") + ".log"
                log_path = os.path.join("logs", log_filename)
                if os.path.exists(log_path):
                    self._send_document(log_path, f"Logs do sistema - {current_log_date.strftime('%d/%m/%Y')}")
                current_log_date += timedelta(days=1)

            db_write = SessionLocal()
            try:
                if text_success:
                    log_entry = RoutineLog(
                        routine_type="TELEGRAM_DAILY_REPORT",
                        target_date=yesterday,
                        status="SUCCESS",
                        execution_time=now_local
                    )
                    db_write.add(log_entry)
                    db_write.commit()
                    logger.info('Relatório - "Telegram diário" OK')
                else:
                    log_entry = RoutineLog(
                        routine_type="TELEGRAM_DAILY_REPORT",
                        target_date=yesterday,
                        status="FAILED",
                        execution_time=now_local
                    )
                    db_write.add(log_entry)
                    db_write.commit()
                    logger.error('Relatório - "Telegram diário" Error')
            except Exception as e:
                db_write.rollback()
                logger.error(f'Relatório - "Telegram diário" DB Error: {e}')
            finally:
                db_write.close()

    def execute_manual_backup(self):
        with self._manual_backup_lock:
            backup_path = self._create_safe_backup()
            if not backup_path:
                logger.error('Backup - "Telegram manual" Error')
                return

            tz = ZoneInfo(settings.TIMEZONE)
            now = datetime.now(tz)
            now_local = now.replace(tzinfo=None)
            now_str = now_local.strftime('%d/%m/%Y %H:%M')
            caption = f"[Backup Manual Solicitado] - {now_str}"

            success = self._send_document(backup_path, caption)

            if os.path.exists(backup_path):
                os.remove(backup_path)

            db_write = SessionLocal()
            try:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_MANUAL_BACKUP",
                    status="SUCCESS" if success else "FAILED",
                    execution_time=now_local
                )
                db_write.add(log_entry)
                db_write.commit()

                if success:
                    logger.info('Backup - "Telegram manual" OK')
                else:
                    logger.error('Backup - "Telegram manual" Error')
            except Exception as e:
                db_write.rollback()
                logger.error(f"Erro ao salvar rotina manual: {e}")
            finally:
                db_write.close()

    def send_manual_report(self, start_date: date, end_date: date):
        with self._manual_report_lock:
            tz = ZoneInfo(settings.TIMEZONE)
            now_local = datetime.now(tz).replace(tzinfo=None)

            db_read = SessionLocal()
            try:
                report_text = self._generate_report_text(
                    db_read,
                    start_date,
                    end_date,
                    title_prefix="Relatório Gerencial Manual -"
                )
            except Exception as e:
                logger.error(f"Erro ao buscar report manual: {e}")
                return
            finally:
                db_read.close()

            text_success = self._send_text(report_text)

            current_log_date = start_date
            while current_log_date <= end_date:
                log_filename = current_log_date.strftime("%d%m%Y") + ".log"
                log_path = os.path.join("logs", log_filename)
                if os.path.exists(log_path):
                    self._send_document(log_path, f"Logs do sistema - {current_log_date.strftime('%d/%m/%Y')}")
                current_log_date += timedelta(days=1)

            db_write = SessionLocal()
            try:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_MANUAL_REPORT",
                    target_date=end_date,
                    status="SUCCESS" if text_success else "FAILED",
                    execution_time=now_local
                )
                db_write.add(log_entry)
                db_write.commit()

                if text_success:
                    logger.info('Relatório - "Telegram manual" OK')
                else:
                    logger.error('Relatório - "Telegram manual" Error')
            except Exception as e:
                db_write.rollback()
                logger.error(f"Erro ao salvar rotina de relatorio manual: {e}")
            finally:
                db_write.close()


telegram_service = TelegramService()