import os
import sqlite3
from datetime import datetime, timedelta, date, time
from typing import Dict, List

import pytz
import requests
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType
from app.domain.models.routine_log import RoutineLog
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User


class TelegramService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.db_path = "spe.db"

    def _create_safe_backup(self) -> str | None:
        if not os.path.exists(self.db_path):
            return None

        try:
            tz = pytz.timezone(settings.TIMEZONE)
            timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
            backup_filename = f"temp_backup_{timestamp}.db"

            src_conn = sqlite3.connect(self.db_path)
            dst_conn = sqlite3.connect(backup_filename)
            src_conn.backup(dst_conn)
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
            return response.status_code == 200
        except Exception:
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
            return response.status_code == 200
        except Exception:
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
        except Exception:
            return "Erro interno ao gerar relatório gerencial."

    def execute_hourly_backup(self):
        backup_path = self._create_safe_backup()
        if not backup_path:
            return

        tz = pytz.timezone(settings.TIMEZONE)
        now_str = datetime.now(tz).strftime('%H:%M')
        caption = f"[Backup Automático] - {now_str}"

        success = self._send_document(backup_path, caption)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        if success:
            db = SessionLocal()
            try:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_HOURLY_BACKUP",
                    status="SUCCESS"
                )
                db.add(log_entry)
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()

    def send_managerial_report(self):
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)
        today = now.date()
        yesterday = today - timedelta(days=1)

        if now.hour < 9:
            return

        db = SessionLocal()
        try:
            today_start = datetime.combine(today, time.min)
            ran_today = db.query(RoutineLog).filter(
                RoutineLog.routine_type == "TELEGRAM_DAILY_REPORT",
                RoutineLog.status == "SUCCESS",
                RoutineLog.execution_time >= today_start
            ).first()

            if ran_today:
                return

            last_success = db.query(RoutineLog).filter(
                RoutineLog.routine_type == "TELEGRAM_DAILY_REPORT",
                RoutineLog.status == "SUCCESS",
                RoutineLog.target_date.isnot(None)
            ).order_by(desc(RoutineLog.target_date)).first()

            if last_success and last_success.target_date:
                start_date = last_success.target_date + timedelta(days=1)
            else:
                start_date = yesterday

            if start_date > yesterday:
                return

            report_text = self._generate_report_text(db, start_date, yesterday)
            text_success = self._send_text(report_text)

            if text_success:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_DAILY_REPORT",
                    target_date=yesterday,
                    status="SUCCESS"
                )
            else:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_DAILY_REPORT",
                    target_date=yesterday,
                    status="FAILED",
                    details=f"Text sent: {text_success}"
                )

            db.add(log_entry)
            db.commit()

        except Exception:
            db.rollback()
        finally:
            db.close()

    def execute_manual_backup(self):
        backup_path = self._create_safe_backup()
        if not backup_path:
            return

        tz = pytz.timezone(settings.TIMEZONE)
        now_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M')
        caption = f"[Backup Manual Solicitado] - {now_str}"

        success = self._send_document(backup_path, caption)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        db = SessionLocal()
        try:
            log_entry = RoutineLog(
                routine_type="TELEGRAM_MANUAL_BACKUP",
                status="SUCCESS" if success else "FAILED"
            )
            db.add(log_entry)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def send_manual_report(self, start_date: date, end_date: date):
        db = SessionLocal()
        try:
            report_text = self._generate_report_text(
                db,
                start_date,
                end_date,
                title_prefix="Relatório Gerencial Manual -"
            )
            text_success = self._send_text(report_text)

            log_entry = RoutineLog(
                routine_type="TELEGRAM_MANUAL_REPORT",
                target_date=end_date,
                status="SUCCESS" if text_success else "FAILED",
                details=f"Text sent: {text_success}"
            )
            db.add(log_entry)
            db.commit()

        except Exception:
            db.rollback()
        finally:
            db.close()


telegram_service = TelegramService()