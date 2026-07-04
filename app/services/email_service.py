import logging
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
from io import BytesIO
from typing import Optional, List, Tuple
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.services.template_service import template_service

logger = logging.getLogger(__name__)


class EmailService:
    def send_payroll_email(self, db, action: str, user_name: str, user_email: str, month: int, year: int,
                           attachment: Optional[BytesIO] = None):
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            logger.warning("SMTP not configured. Skipping payroll email.")
            return

        try:
            maintainers = db.query(User).filter(User.role == UserRole.MAINTAINER, User.is_active == True,
                                                User.email.isnot(None)).all()
            to_emails = [m.email for m in maintainers if m.email]

            if not to_emails:
                logger.warning("No maintainers with emails to send payroll email.")
                return

            subject = f"Folha de Ponto - {month:02d}/{year}"

            if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
                subject = f"Folha de Ponto DEV - {month:02d}/{year}"

            tz = ZoneInfo(settings.TIMEZONE)
            now_str = datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S")

            body_text = (
                f"Ação: {action}\n"
                f"Usuário: {user_name} ({user_email})\n"
                f"Data e Hora: {now_str}\n"
                f"Mês/Ano: {month:02d}/{year}\n"
            )

            msg = MIMEMultipart()

            raw_sender = settings.EMAIL_FROM or settings.SMTP_USER
            if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
                name, addr = parseaddr(raw_sender if raw_sender else "")
                email_address = addr if addr else (raw_sender if raw_sender else "")
                display_name = f"DEVELOPMENT {name}".strip() if name else "DEVELOPMENT"
                msg['From'] = formataddr((display_name, email_address))
            else:
                msg['From'] = raw_sender

            msg['To'] = ", ".join(to_emails)
            msg['Subject'] = subject
            msg.attach(MIMEText(body_text, 'plain'))

            if attachment:
                filename = f"Folha_{month:02d}_{year}.xlsx"
                part = MIMEApplication(attachment.getvalue(), Name=filename)
                part['Content-Disposition'] = f'attachment; filename="{filename}"'
                msg.attach(part)

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg['From'], to_emails, msg.as_string())
            server.quit()
            logger.info(f"Payroll email sent successfully for {action} {month:02d}/{year}")
        except smtplib.SMTPException as e:
            logger.error(f"Failed to send payroll email (SMTP error): {e}")
        except Exception as e:
            logger.error(f"Failed to send payroll email: {e}")

    def send_email(self, to_emails: List[str], attachments: List[Tuple[str, str]], report_html: str,
                   period_text: str) -> bool:
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]) or not to_emails:
            return False

        try:
            msg = MIMEMultipart()

            raw_sender = settings.EMAIL_FROM or settings.SMTP_USER
            tz = ZoneInfo(settings.TIMEZONE)
            current_date = datetime.now(tz).strftime("%d/%m/%Y")
            base_subject = f"Backup SPE e Relatórios - {current_date}"

            if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
                name, addr = parseaddr(raw_sender if raw_sender else "")
                email_address = addr if addr else (raw_sender if raw_sender else "")
                display_name = f"DEVELOPMENT {name}".strip() if name else "DEVELOPMENT"
                msg['From'] = formataddr((display_name, email_address))
                current_time = datetime.now(tz).strftime("%H:%M:%S")
                msg['Subject'] = f"Backup SPE DEV - {current_date} {current_time}"
            else:
                if raw_sender:
                    msg['From'] = raw_sender
                else:
                    msg['From'] = ""
                msg['Subject'] = base_subject

            msg['To'] = ", ".join(to_emails)

            body_html = template_service.get_backup_email_html(period_text, report_html)

            msg.attach(MIMEText(body_html, 'html'))

            import os
            for file_path, filename in attachments:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        part = MIMEApplication(f.read(), Name=filename)
                        part['Content-Disposition'] = f'attachment; filename="{filename}"'
                        msg.attach(part)

            if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD or not settings.SMTP_PORT:
                return False

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg['From'], to_emails, msg.as_string())
            server.quit()
            return True

        except smtplib.SMTPException as e:
            logger.error(f"Erro SMTP: {e}")
            return False


email_service = EmailService()


def dispatch_payroll_email(action: str, user_name: str, user_email: str, month: int, year: int, current_user_id: int):
    from app.database.session import get_db_session
    from app.services.excel_service import excel_service

    try:
        with get_db_session() as db:
            attachment = None
            if action == "Fechamento":
                current_user = db.query(User).get(current_user_id)
                if current_user:
                    attachment = excel_service.generate_excel_report(db, month, year, None, current_user)

            email_service.send_payroll_email(db, action, user_name, user_email, month, year, attachment)
    except Exception as e:
        logger.error(f"Error in dispatch_payroll_email: {e}")
