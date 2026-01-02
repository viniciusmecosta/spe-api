import logging
import os
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackupService:
    def send_database_backup(self):
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.EMAIL_TO]):
            logger.warning("Configurações de e-mail incompletas. Backup ignorado.")
            return

        db_file = "spe.db"
        if not os.path.exists(db_file):
            logger.error(f"Arquivo de banco de dados não encontrado: {db_file}")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = settings.EMAIL_FROM or settings.SMTP_USER
            msg['To'] = settings.EMAIL_TO

            tz = pytz.timezone(settings.TIMEZONE)
            now = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
            msg['Subject'] = f"Backup SPE - {now}"

            body = f"Segue em anexo o backup do banco de dados (spe.db) gerado em {now}."
            msg.attach(MIMEText(body, 'plain'))

            with open(db_file, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f"attachment; filename=spe_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                )
                msg.attach(part)

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            text = msg.as_string()
            server.sendmail(msg['From'], msg['To'], text)
            server.quit()

            logger.info("Backup enviado por e-mail com sucesso.")

        except Exception as e:
            logger.error(f"Erro ao enviar backup por e-mail: {str(e)}")


backup_service = BackupService()
