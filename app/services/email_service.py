import logging
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from io import BytesIO
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.services.template_service import template_service

logger = logging.getLogger(__name__)


class EmailService:
    def send_payroll_email(self, action: str, user_name: str, month: int, year: int,
                           attachment: BytesIO | None = None, to_emails: list[str] = None):
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            logger.warning("SMTP not configured. Skipping payroll email.")
            return

        try:
            if not to_emails:
                logger.warning("No maintainers with emails to send payroll email.")
                return

            subject = f"Folha de Ponto - {month:02d}/{year}"

            if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
                subject = f"Folha de Ponto DEV - {month:02d}/{year}"

            tz = ZoneInfo(settings.TIMEZONE)
            now_str = datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S")

            body_html = template_service.get_payroll_email_html(
                action=action,
                user_name=user_name,
                month=month,
                year=year,
                date_str=now_str
            )

            msg = self._build_payroll_message(
                to_emails=to_emails,
                subject=subject,
                body_html=body_html,
                attachment=attachment,
                month=month,
                year=year
            )

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg['From'], to_emails, msg.as_string())
            server.quit()
            logger.info(f"Payroll email sent successfully for {action} {month:02d}/{year}")
        except smtplib.SMTPException as e:
            logger.exception(f"Failed to send payroll email (SMTP error): {e}")
        except Exception as e:
            logger.exception(f"Failed to send payroll email: {e}")

    def send_email(self, to_emails: list[str], attachments: list[tuple[str, str]], report_html: str,
                   period_text: str) -> bool:
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]) or not to_emails:
            return False

        try:
            msg = self._build_backup_message(
                to_emails=to_emails,
                attachments=attachments,
                report_html=report_html,
                period_text=period_text
            )

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
            logger.exception(f"Erro SMTP: {e}")
            return False

    def _get_sender_address(self) -> str:
        raw_sender = settings.EMAIL_FROM or settings.SMTP_USER
        if not raw_sender:
            raw_sender = ""

        if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
            name, addr = parseaddr(raw_sender)

            if addr:
                email_address = addr
            else:
                email_address = raw_sender

            if name:
                display_name = f"DEVELOPMENT {name}".strip()
            else:
                display_name = "DEVELOPMENT"

            return formataddr((display_name, email_address))

        return raw_sender

    def _build_payroll_message(
            self,
            to_emails: list[str],
            subject: str,
            body_html: str,
            attachment: BytesIO | None,
            month: int,
            year: int
    ) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg['From'] = self._get_sender_address()
        msg['To'] = ", ".join(to_emails)
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))

        if attachment:
            filename = f"Folha_{month:02d}_{year}.xlsx"
            part = MIMEApplication(attachment.getvalue(), Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            msg.attach(part)

        return msg

    def _build_backup_message(
            self,
            to_emails: list[str],
            attachments: list[tuple[str, str]],
            report_html: str,
            period_text: str
    ) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg['From'] = self._get_sender_address()
        msg['To'] = ", ".join(to_emails)

        tz = ZoneInfo(settings.TIMEZONE)
        current_date = datetime.now(tz).strftime("%d/%m/%Y")
        if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
            current_time = datetime.now(tz).strftime("%H:%M:%S")
            msg['Subject'] = f"Backup SPE DEV - {current_date} {current_time}"
        else:
            msg['Subject'] = f"Backup SPE e Relatórios - {current_date}"

        body_html = template_service.get_backup_email_html(period_text, report_html)
        msg.attach(MIMEText(body_html, 'html'))

        import os
        for file_path, filename in attachments:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=filename)
                    part['Content-Disposition'] = f'attachment; filename="{filename}"'
                    msg.attach(part)

        return msg


email_service = EmailService()


def dispatch_payroll_email(action: str, user_name: str, month: int, year: int, to_emails: list[str]):
    try:
        email_service.send_payroll_email(action, user_name, month, year, None, to_emails)
    except Exception as e:
        logger.exception(f"Error in dispatch_payroll_email: {e}")
