import logging
import os
import pytz
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy import func
from typing import Dict, List

from app.core.config import settings
from app.database.session import SessionLocal
from app.domain.models.enums import RecordType
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User

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
        except Exception as e:
            logger.error(f"Erro no backup: {e}")
            return None

    def _get_yesterday_activity_html(self) -> str:
        db = SessionLocal()
        try:
            tz = pytz.timezone(settings.TIMEZONE)
            yesterday = (datetime.now(tz) - timedelta(days=1)).date()
            formatted_date = yesterday.strftime("%d/%m/%Y")

            records = (
                db.query(TimeRecord, User)
                .join(User, TimeRecord.user_id == User.id)
                .filter(func.date(TimeRecord.record_datetime) == yesterday)
                .order_by(User.name, TimeRecord.record_datetime)
                .all()
            )

            html = f"""
            <h3 style="color: #333; margin-bottom: 10px;">Relatório de Pontos - {formatted_date}</h3>
            """

            if not records:
                return html + "<p><em>Sem registros de ponto ontem.</em></p>"

            user_activity: Dict[str, List[str]] = {}
            for record, user in records:
                if user.name not in user_activity:
                    user_activity[user.name] = []

                time_str = record.record_datetime.strftime("%H:%M")
                type_label = "E" if record.record_type == RecordType.ENTRY else "S"

                user_activity[user.name].append(f"{time_str} ({type_label})")

            html += """
            <table style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px; color: #333;">
                <thead>
                    <tr style="background-color: #f4f4f4; text-align: left;">
                        <th style="padding: 8px; border: 1px solid #ddd; width: 40%;">Colaborador</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Registros (E=Entrada, S=Saída)</th>
                    </tr>
                </thead>
                <tbody>
            """

            for name, punches in user_activity.items():
                punches_str = "  |  ".join(punches)
                html += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>{name}</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{punches_str}</td>
                    </tr>
                """

            html += """
                </tbody>
            </table>
            """
            return html

        except Exception as e:
            logger.error(f"Erro no relatório: {e}")
            return f"<p><em>Erro ao gerar relatório.</em></p>"
        finally:
            db.close()

    def _send_email(self, file_path: str, filename: str, report_html: str):
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.EMAIL_TO]):
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = settings.EMAIL_FROM or settings.SMTP_USER
            msg['To'] = settings.EMAIL_TO

            tz = pytz.timezone(settings.TIMEZONE)
            current_date = datetime.now(tz).strftime("%d/%m/%Y")

            msg['Subject'] = f"Backup SPE e Relatório - {current_date}"

            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <p>Prezados,</p>
                <p>Segue em anexo a cópia de segurança do banco de dados.</p>
                {report_html}
                <br>
                <p style="font-size: 12px; color: #777;">Atenciosamente,<br>SPE - Sistema de Ponto Eletrônico</p>
            </body>
            </html>
            """

            msg.attach(MIMEText(body_html, 'html'))

            with open(file_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=filename)
                part['Content-Disposition'] = f'attachment; filename="{filename}"'
                msg.attach(part)

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg['From'], msg['To'], msg.as_string())
            server.quit()

            logger.info("Email enviado com sucesso.")

        except Exception as e:
            logger.error(f"Erro ao enviar e-mail: {e}")

    def send_database_backup(self):
        db_file = "spe.db"
        if not os.path.exists(db_file):
            logger.error("Banco não encontrado.")
            return

        backup_path = self._create_safe_backup(db_file)
        if not backup_path:
            return

        try:
            report_html = self._get_yesterday_activity_html()
            filename = "spe.db"
            self._send_email(backup_path, filename, report_html)
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)


backup_service = BackupService()
