import logging
import os
import pytz
import smtplib
import sqlite3
import uuid
from datetime import datetime, timedelta, date, time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import Dict, List

from app.core.config import settings
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType
from app.domain.models.routine_log import RoutineLog
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User

logger = logging.getLogger("uvicorn.info")


class BackupService:
    def _create_safe_backup(self, source_db: str) -> str | None:
        try:
            tz = pytz.timezone(settings.TIMEZONE)
            timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            backup_filename = f"temp_backup_{timestamp}_{unique_id}.db"

            src_conn = sqlite3.connect(source_db)
            dst_conn = sqlite3.connect(backup_filename)

            src_conn.backup(dst_conn)

            dst_conn.close()
            src_conn.close()

            return backup_filename
        except Exception:
            return None

    def _generate_daily_report_html(self, db: Session, target_date: date) -> str:
        try:
            formatted_date = target_date.strftime("%d/%m/%Y")
            day_name_map = {
                0: "Segunda-feira", 1: "Terça-feira", 2: "Quarta-feira", 3: "Quinta-feira",
                4: "Sexta-feira", 5: "Sábado", 6: "Domingo"
            }
            day_name = day_name_map[target_date.weekday()]

            start_local = datetime.combine(target_date, time.min)
            end_local = datetime.combine(target_date, time.max)

            records = (
                db.query(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .filter(TimeRecord.record_datetime >= start_local)
                .filter(TimeRecord.record_datetime <= end_local)
                .order_by(User.name, TimeRecord.record_datetime)
                .all()
            )

            html = f"<div style='margin-bottom: 20px;'>"
            html += f"<h3 style=\"color: #333; margin-bottom: 5px;\">Relatório de Pontos - {day_name}, {formatted_date}</h3>"

            if not records:
                html += "<p style='font-size: 13px; color: #666;'><em>Sem registros de ponto neste dia.</em></p></div>"
                return html

            user_activity: Dict[str, List[str]] = {}
            for record, user in records:
                if user.name not in user_activity:
                    user_activity[user.name] = []

                time_str = record.record_datetime.strftime("%H:%M")
                type_label = "E" if record.record_type == RecordType.ENTRY else "S"

                user_activity[user.name].append(f"{time_str} ({type_label})")

            html += "<table style=\"width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px; color: #333;\">"
            html += "<thead><tr style=\"background-color: #f4f4f4; text-align: left;\">"
            html += "<th style=\"padding: 8px; border: 1px solid #ddd; width: 40%;\">Colaborador</th>"
            html += "<th style=\"padding: 8px; border: 1px solid #ddd;\">Registros (E=Entrada, S=Saída)</th>"
            html += "</tr></thead><tbody>"

            for name, punches in user_activity.items():
                punches_str = "  |  ".join(punches)
                html += f"<tr><td style=\"padding: 8px; border: 1px solid #ddd;\"><strong>{name}</strong></td><td style=\"padding: 8px; border: 1px solid #ddd;\">{punches_str}</td></tr>"

            html += "</tbody></table>"
            html += "</div><hr style='border: 0; border-top: 1px solid #eee; margin: 20px 0;'>"
            return html

        except Exception as e:
            logger.error(f"Erro HTML Report: {e}")
            return f"<p><em>Erro ao gerar relatório para {target_date}.</em></p>"

    def _send_email(self, file_path: str, filename: str, report_html: str, period_text: str) -> bool:
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.EMAIL_TO]):
            return False

        try:
            msg = MIMEMultipart()

            raw_sender = settings.EMAIL_FROM or settings.SMTP_USER
            tz = pytz.timezone(settings.TIMEZONE)
            current_date = datetime.now(tz).strftime("%d/%m/%Y")
            base_subject = f"Backup SPE e Relatórios - {current_date}"

            if settings.ENVIRONMENT.lower() == "dev":
                name, addr = parseaddr(raw_sender)
                email_address = addr if addr else raw_sender
                display_name = f"DEVELOPMENT {name}".strip() if name else "DEVELOPMENT"
                msg['From'] = formataddr((display_name, email_address))
                msg['Subject'] = f"[DEV] {base_subject}"
            else:
                msg['From'] = raw_sender
                msg['Subject'] = base_subject

            msg['To'] = settings.EMAIL_TO

            body_html = (
                f"<html><body style=\"font-family: Arial, sans-serif; color: #333;\">"
                f"<p>Prezados,</p>"
                f"<p>Segue em anexo a cópia de segurança do banco de dados.</p>"
                f"<p>{period_text}</p>"
                f"<br>"
                f"{report_html}"
                f"<br>"
                f"<p style=\"font-size: 12px; color: #777;\">Atenciosamente,<br>SPE - Sistema de Ponto Eletrônico</p>"
                f"</body></html>"
            )

            msg.attach(MIMEText(body_html, 'html'))

            with open(file_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=filename)
                part['Content-Disposition'] = f'attachment; filename="{filename}"'
                msg.attach(part)

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg['From'], msg['To'], msg.as_string())
            server.quit()
            return True

        except Exception as e:
            logger.error(f"Erro SMTP: {e}")
            return False

    def send_database_backup(self, db: Session = None) -> bool:
        session = db or SessionLocal()
        try:
            tz = pytz.timezone(settings.TIMEZONE)
            now = datetime.now(tz)
            yesterday = now.date() - timedelta(days=1)

            full_report_html = self._generate_daily_report_html(session, yesterday)
            fmt_start = yesterday.strftime("%d/%m/%Y")
            period_text = f"Abaixo está o relatório do dia {fmt_start}:"
        finally:
            if db is None:
                session.close()

        backup_path = self._create_safe_backup("spe.db")
        if not backup_path:
            logger.error('Backup - "Email manual" Error')
            return False

        success = self._send_email(backup_path, "spe.db", full_report_html, period_text)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        if success:
            logger.info('Backup - "Email manual" OK')
            return True
        else:
            logger.error('Backup - "Email manual" Error')
            return False

    def run_daily_backup_routine(self):
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)
        today = now.date()
        yesterday = today - timedelta(days=1)

        if now.hour < 9:
            return

        db_read = SessionLocal()
        try:
            ran_today = db_read.query(RoutineLog).filter(
                RoutineLog.routine_type == "EMAIL_DAILY_BACKUP",
                RoutineLog.status == "SUCCESS",
                RoutineLog.target_date == yesterday
            ).first()

            if ran_today:
                return

            last_success = db_read.query(RoutineLog).filter(
                RoutineLog.routine_type == "EMAIL_DAILY_BACKUP",
                RoutineLog.status == "SUCCESS",
                RoutineLog.target_date.isnot(None)
            ).order_by(desc(RoutineLog.target_date)).first()

            if last_success and last_success.target_date:
                start_date = last_success.target_date + timedelta(days=1)
            else:
                start_date = yesterday

            if start_date > yesterday:
                start_date = yesterday

            full_report_html = ""
            current_check_date = start_date
            while current_check_date <= yesterday:
                daily_html = self._generate_daily_report_html(db_read, current_check_date)
                full_report_html += daily_html
                current_check_date += timedelta(days=1)

            if not full_report_html:
                full_report_html = "<p><em>Nenhum período pendente para relatório.</em></p>"

            fmt_start = start_date.strftime("%d/%m/%Y")
            fmt_end = yesterday.strftime("%d/%m/%Y")
            if start_date < yesterday:
                period_text = f"Abaixo estão os relatórios dos dias {fmt_start} a {fmt_end}:"
            else:
                period_text = f"Abaixo está o relatório do dia {fmt_start}:"
        except Exception as e:
            logger.error(f"Erro check backup diário: {e}")
            return
        finally:
            db_read.close()

        backup_path = self._create_safe_backup("spe.db")
        if not backup_path:
            logger.error('Backup - "Email diário" Error')
            return

        success = self._send_email(backup_path, "spe.db", full_report_html, period_text)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        db_write = SessionLocal()
        try:
            if success:
                log_entry = RoutineLog(
                    routine_type="EMAIL_DAILY_BACKUP",
                    target_date=yesterday,
                    status="SUCCESS"
                )
                db_write.add(log_entry)
                db_write.commit()
                logger.info('Backup - "Email diário" OK')
            else:
                log_entry = RoutineLog(
                    routine_type="EMAIL_DAILY_BACKUP",
                    target_date=yesterday,
                    status="FAILED"
                )
                db_write.add(log_entry)
                db_write.commit()
                logger.error('Backup - "Email diário" Error')
        except Exception as e:
            db_write.rollback()
            logger.error(f'Backup - "Email diário" DB Error: {e}')
        finally:
            db_write.close()


backup_service = BackupService()