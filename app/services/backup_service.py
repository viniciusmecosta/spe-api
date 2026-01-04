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
            current_dt = datetime.now(tz)
            formatted_date = current_dt.strftime("%d/%m/%Y às %H:%M")
            msg['Subject'] = f"Backup Banco MH7 Ponto - {formatted_date}"
            body = (
                f"Olá,\n\n"
                f"O backup automático do banco de dados do sistema MH7 Ponto foi realizado com sucesso.\n\n"
                f"📅 Data/Hora da Geração: {formatted_date}\n"
                f"📂 Arquivo: spe.db (Anexado)\n\n"
                f"Mantenha este arquivo seguro para garantir a integridade dos dados.\n\n"
                f"Sistema de Ponto Eletrônico - Notificação Automática"
            )
            msg.attach(MIMEText(body, 'plain'))

            with open(db_file, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                filename = f"spe_backup_{current_dt.strftime('%Y%m%d_%H%M')}.db"
                part.add_header(
                    'Content-Disposition',
                    f"attachment; filename={filename}",
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
