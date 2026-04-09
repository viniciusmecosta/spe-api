import logging
import os
import smtplib
import sqlite3
from datetime import datetime, timedelta, date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
from typing import Dict, List

import pytz
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.domain.models.audit import AuditLog
from app.domain.models.enums import RecordType
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)


class BackupService:
    def _create_safe_backup(self, source_db: str) -> str | None:
        try:
            tz = pytz.timezone(settings.TIMEZONE)
            timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
            backup_filename = f"temp_backup_{timestamp}.db"

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

            start_local = datetime.combine(target_date, datetime.min.time())
            end_local = datetime.combine(target_date, datetime.max.time())

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
            logger.error(f"Erro ao gerar HTML do dia {target_date}: {e}")
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

        except smtplib.SMTPException as e:
            logger.error(f"Erro de protocolo SMTP ao enviar email: {e}")
            return False
        except TimeoutError as e:
            logger.error(f"Timeout ao tentar conectar ou enviar o email (arquivo muito grande ou rede instavel): {e}")
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao enviar email: {e}")
            return False

    def send_database_backup(self, db: Session = None) -> bool:
        db_file = "spe.db"
        if not os.path.exists(db_file):
            return False

        session = db or SessionLocal()
        try:
            tz = pytz.timezone(settings.TIMEZONE)
            now = datetime.now(tz)
            today = now.date()
            yesterday = today - timedelta(days=1)

            last_backup = session.query(AuditLog).filter(
                AuditLog.action == "DAILY_BACKUP"
            ).order_by(AuditLog.timestamp.desc()).first()

            start_date = yesterday

            if last_backup:
                last_backup_local = last_backup.timestamp
                if last_backup_local.tzinfo is not None:
                    last_backup_local = last_backup_local.astimezone(tz)
                start_date = last_backup_local.date()

            if start_date > yesterday:
                start_date = yesterday

            full_report_html = ""
            current_check_date = start_date

            while current_check_date <= yesterday:
                daily_html = self._generate_daily_report_html(session, current_check_date)
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

        finally:
            if db is None:
                session.close()
            else:
                session.commit()

        backup_path = self._create_safe_backup(db_file)
        if not backup_path:
            return False

        success = False
        try:
            filename = "spe.db"
            success = self._send_email(backup_path, filename, full_report_html, period_text)
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)

        return success

    def run_daily_backup_routine(self):
        tz = pytz.timezone(settings.TIMEZONE)
        now = datetime.now(tz)
        today = now.date()

        if now.hour < 9:
            return

        db_check = SessionLocal()
        try:
            last_backup = db_check.query(AuditLog).filter(
                AuditLog.action == "DAILY_BACKUP"
            ).order_by(AuditLog.timestamp.desc()).first()

            if last_backup:
                log_time = last_backup.timestamp
                if log_time.tzinfo is not None:
                    log_time = log_time.astimezone(tz)

                log_date = log_time.date()
                if log_date == today:
                    return

            system_user = db_check.query(User).first()
            valid_user_id = system_user.id if system_user else 1
        except Exception as e:
            logger.error(f"Erro na checagem da rotina de backup: {e}")
            return
        finally:
            db_check.close()

        sent = self.send_database_backup()

        if sent:
            db_log = SessionLocal()
            try:
                target_email = settings.EMAIL_TO or "Email nao configurado"
                audit_service.log(
                    db=db_log,
                    user_id=valid_user_id,
                    actor_id=valid_user_id,
                    actor_name="Sistema",
                    action="DAILY_BACKUP",
                    entity="SYSTEM",
                    details=f"Backup diario enviado para: {target_email}",
                    new_data={"target_email": target_email}
                )
            except Exception as e:
                logger.error(f"Erro ao salvar log do backup: {e}")
            finally:
                db_log.close()


backup_service = BackupService()