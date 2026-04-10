import os
import sqlite3
import requests
from datetime import datetime, timedelta, date, time
from typing import Dict, List

import pytz
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User
from app.domain.models.routine_log import RoutineLog


class TelegramService:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
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

    def _generate_report_text(self, db: Session, start_date: date, end_date: date,
                              title_prefix: str = "Rotina Gerencial - Fechamento") -> str:
        try:
            start_dt = datetime.combine(start_date, time.min)
            end_dt = datetime.combine(end_date, time.max)

            records = (
                db.query(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .filter(TimeRecord.record_datetime >= start_dt)
                .filter(TimeRecord.record_datetime <= end_dt)
                .order_by(User.name, TimeRecord.record_datetime)
                .all()
            )

            fmt_start = start_date.strftime("%d/%m/%Y")
            fmt_end = end_date.strftime("%d/%m/%Y")

            if start_date == end_date:
                title_date = fmt_start
            else:
                title_date = f"{fmt_start} a {fmt_end}"

            text = f"📊 <b>{title_prefix} {title_date}</b>\n\n"

            if not records:
                text += "Sem registros de ponto no período.\n\n"
                text += "<i>A cópia de segurança consolidada do período segue em anexo.</i>"
                return text

            user_activity: Dict[str, List[str]] = {}
            for record, user in records:
                if user.name not in user_activity:
                    user_activity[user.name] = []

                time_str = record.record_datetime.strftime("%H:%M")
                marker = "🟢" if record.record_type == RecordType.ENTRY else "🔴"

                if start_date != end_date:
                    date_str = record.record_datetime.strftime("%d/%m")
                    user_activity[user.name].append(f"{marker} {date_str} {time_str}")
                else:
                    user_activity[user.name].append(f"{marker} {time_str}")

            for name, punches in user_activity.items():
                punches_str = " | ".join(punches)
                text += f"<b>{name}</b>\n{punches_str}\n\n"

            text += "<i>A cópia de segurança consolidada do período segue em anexo.</i>"
            return text.strip()
        except Exception:
            return "Erro interno ao gerar relatório gerencial."

    def execute_hourly_backup(self):
        backup_path = self._create_safe_backup()
        if not backup_path:
            return

        tz = pytz.timezone(settings.TIMEZONE)
        now_str = datetime.now(tz).strftime('%H:%M')
        caption = f"🗄️ Backup Automático - {now_str}"

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

            doc_success = False
            backup_path = self._create_safe_backup()
            if backup_path:
                doc_success = self._send_document(backup_path, "🗄️ Cópia de Segurança Consolidada")
                if os.path.exists(backup_path):
                    os.remove(backup_path)

            if text_success and doc_success:
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
                    details=f"Text sent: {text_success}, Doc sent: {doc_success}"
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
        caption = f"🗄️ Backup Manual Solicitado - {now_str}"

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

            doc_success = False
            backup_path = self._create_safe_backup()
            if backup_path:
                doc_success = self._send_document(backup_path,
                                                  f"🗄️ Banco de Dados Consolidado ({start_date.strftime('%d/%m')} a {end_date.strftime('%d/%m')})")
                if os.path.exists(backup_path):
                    os.remove(backup_path)

            log_entry = RoutineLog(
                routine_type="TELEGRAM_MANUAL_REPORT",
                target_date=end_date,
                status="SUCCESS" if (text_success and doc_success) else "FAILED",
                details=f"Text sent: {text_success}, Doc sent: {doc_success}"
            )
            db.add(log_entry)
            db.commit()

        except Exception:
            db.rollback()
        finally:
            db.close()


telegram_service = TelegramService()