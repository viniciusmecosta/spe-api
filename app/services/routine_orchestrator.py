import logging
import os
from datetime import datetime, timedelta
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.logger import get_log_path
from app.database.session import get_db_session
from app.domain.models.enums import UserRole
from app.domain.models.routine_log import RoutineLog
from app.domain.models.user import User
from app.services.backup_service import backup_service
from app.services.daily_report_service import daily_report_service
from app.services.email_service import email_service
from app.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)
DATE_FORMAT = "%d/%m/%Y"

class RoutineOrchestrator:
    def execute_hourly_backup_telegram(self):
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)

        if now_local.hour < settings.HOURLY_BACKUP_START_HOUR or now_local.hour > settings.HOURLY_BACKUP_END_HOUR:
            return

        try:
            with get_db_session() as db_read:
                current_hour_start_local = now_local.replace(minute=0, second=0, microsecond=0)

                exists = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "TELEGRAM_HOURLY_BACKUP",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.execution_time >= current_hour_start_local
                ).first()
                if exists:
                    return
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao verificar backup horário Telegram: {e}")
            return

        backup_path = backup_service.create_safe_backup()
        if not backup_path:
            logger.exception('Backup - "Telegram horário" Error')
            return

        now_str = now_local.strftime('%H:%M')
        caption = f"[Backup Automático] - {now_str}"

        success = telegram_service.send_document(backup_path, caption)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        try:
            with get_db_session() as db_write:
                if success:
                    log_entry = RoutineLog(
                        routine_type="TELEGRAM_HOURLY_BACKUP",
                        status="SUCCESS",
                        execution_time=now_local
                    )
                    db_write.add(log_entry)
                else:
                    logger.exception('Backup - "Telegram horário" Error')
        except SQLAlchemyError as e:
            logger.exception(f'Backup - "Telegram horário" DB Error: {e}')

    def send_managerial_report_telegram(self):
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        if now_local.hour < settings.DAILY_REPORT_HOUR:
            return

        try:
            with get_db_session() as db_read:
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

                start_date = yesterday
                if last_success and last_success.target_date:
                    start_date = last_success.target_date + timedelta(days=1)

                if start_date > yesterday:
                    start_date = yesterday

                report_text = telegram_service.generate_report_text(db_read, start_date, yesterday)
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao gerar report gerencial Telegram: {e}")
            return

        text_success = telegram_service.send_text(report_text)

        current_log_date = start_date
        while current_log_date <= yesterday:
            log_path = get_log_path(current_log_date)
            if os.path.exists(log_path):
                telegram_service.send_document(log_path, f"Logs do sistema - {current_log_date.strftime(DATE_FORMAT)}")
            current_log_date += timedelta(days=1)

        try:
            with get_db_session() as db_write:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_DAILY_REPORT",
                    target_date=yesterday,
                    status="SUCCESS" if text_success else "FAILED",
                    execution_time=now_local
                )
                db_write.add(log_entry)
                if not text_success:
                    logger.exception('Relatório - "Telegram diário" Error')
        except SQLAlchemyError as e:
            logger.exception(f'Relatório - "Telegram diário" DB Error: {e}')

    def _generate_daily_backup_report(self, db_read, start_date, yesterday):
        full_report_html = ""
        attachments = []
        current_check_date = start_date
        while current_check_date <= yesterday:
            daily_html = daily_report_service.generate_daily_report_html(db_read, current_check_date)
            full_report_html += daily_html
            log_path = get_log_path(current_check_date)
            if os.path.exists(log_path):
                attachments.append((log_path, f"log_{current_check_date.strftime('%d%m%Y')}.log"))
            current_check_date += timedelta(days=1)
        if not full_report_html:
            full_report_html = "<p><em>Nenhum período pendente para relatório.</em></p>"
        fmt_start = start_date.strftime(DATE_FORMAT)
        fmt_end = yesterday.strftime(DATE_FORMAT)
        if start_date < yesterday:
            period_text = f"Abaixo estão os relatórios e logs dos dias {fmt_start} a {fmt_end}:"
        else:
            period_text = f"Abaixo está o relatório e log do dia {fmt_start}:"
        return full_report_html, attachments, period_text

    def run_daily_backup_routine_email(self):
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        if now_local.hour < settings.DAILY_REPORT_HOUR:
            return

        try:
            with get_db_session() as db_read:
                ran_today = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "EMAIL_DAILY_BACKUP",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.target_date == yesterday
                ).first()

                if ran_today:
                    return

                maintainers = db_read.query(User).filter(User.role == UserRole.MAINTAINER, User.is_active == True,
                                                         User.email.isnot(None)).all()
                to_emails = [m.email for m in maintainers if m.email]

                if not to_emails:
                    return

                last_success = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "EMAIL_DAILY_BACKUP",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.target_date.isnot(None)
                ).order_by(desc(RoutineLog.target_date)).first()

                start_date = yesterday
                if last_success and last_success.target_date:
                    start_date = last_success.target_date + timedelta(days=1)

                if start_date > yesterday:
                    start_date = yesterday

                full_report_html, attachments, period_text = self._generate_daily_backup_report(db_read, start_date,
                                                                                                yesterday)
        except SQLAlchemyError as e:
            logger.exception(f"Erro check backup diário: {e}")
            return

        backup_path = backup_service.create_safe_backup()
        if not backup_path:
            logger.exception('Backup - "Email diário" Error')
            return

        attachments.insert(0, (backup_path, "spe.db"))

        success = email_service.send_email(to_emails, attachments, full_report_html, period_text)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        try:
            with get_db_session() as db_write:
                log_entry = RoutineLog(
                    routine_type="EMAIL_DAILY_BACKUP",
                    target_date=yesterday,
                    status="SUCCESS" if success else "FAILED",
                    execution_time=now_local
                )
                db_write.add(log_entry)
                if not success:
                    logger.exception('Backup - "Email diário" Error')
        except SQLAlchemyError as e:
            logger.exception(f'Backup - "Email diário" DB Error: {e}')

    def clean_old_logs(self, days_to_keep: int = None):
        days_to_keep = days_to_keep or settings.ROUTINE_LOG_RETENTION_DAYS
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        today = now_local.date()

        try:
            with get_db_session() as db_read:
                ran_today = db_read.query(RoutineLog).filter(
                    RoutineLog.routine_type == "CLEANUP_ROUTINE_LOGS",
                    RoutineLog.status == "SUCCESS",
                    RoutineLog.target_date == today
                ).first()

                if ran_today:
                    return
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao verificar rotina de limpeza: {e}")
            return

        try:
            with get_db_session() as db_write:
                cutoff_date = now_local - timedelta(days=days_to_keep)
                deleted_count = db_write.query(RoutineLog).filter(RoutineLog.execution_time < cutoff_date).delete()

                log_entry = RoutineLog(
                    routine_type="CLEANUP_ROUTINE_LOGS",
                    target_date=today,
                    status="SUCCESS",
                    execution_time=now_local,
                    details=f"{deleted_count} logs apagados"
                )
                db_write.add(log_entry)
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao limpar routine_logs: {e}")

    def execute_manual_backup_telegram(self):
        backup_path = backup_service.create_safe_backup()
        if not backup_path:
            logger.exception('Backup - "Telegram manual" Error')
            return

        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        now_str = now_local.strftime('%d/%m/%Y %H:%M')
        caption = f"[Backup Manual Solicitado] - {now_str}"

        success = telegram_service.send_document(backup_path, caption)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        try:
            with get_db_session() as db_write:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_MANUAL_BACKUP",
                    status="SUCCESS" if success else "FAILED",
                    execution_time=now_local
                )
                db_write.add(log_entry)
                if not success:
                    logger.exception('Backup - "Telegram manual" Error')
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao salvar rotina manual: {e}")

    def send_manual_report_telegram(self, start_date, end_date):
        tz = ZoneInfo(settings.TIMEZONE)
        now_local = datetime.now(tz).replace(tzinfo=None)

        try:
            with get_db_session() as db_read:
                report_text = telegram_service.generate_report_text(
                    db_read,
                    start_date,
                    end_date,
                    title_prefix="Relatório Gerencial Manual -"
                )
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao buscar report manual: {e}")
            return

        text_success = telegram_service.send_text(report_text)

        current_log_date = start_date
        while current_log_date <= end_date:
            log_path = get_log_path(current_log_date)
            if os.path.exists(log_path):
                telegram_service.send_document(log_path, f"Logs do sistema - {current_log_date.strftime(DATE_FORMAT)}")
            current_log_date += timedelta(days=1)

        try:
            with get_db_session() as db_write:
                log_entry = RoutineLog(
                    routine_type="TELEGRAM_MANUAL_REPORT",
                    target_date=end_date,
                    status="SUCCESS" if text_success else "FAILED",
                    execution_time=now_local
                )
                db_write.add(log_entry)

                if not text_success:
                    logger.exception('Relatório - "Telegram manual" Error')
        except SQLAlchemyError as e:
            logger.exception(f"Erro ao salvar rotina de relatorio manual: {e}")

    def send_manual_backup_email(self, db) -> bool:
        from fastapi import HTTPException
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            raise HTTPException(status_code=400,
                                detail="Serviço de email não configurado. Verifique as variáveis de ambiente (SMTP).")

        try:
            session = db if db else get_db_session().__enter__()
            maintainers = session.query(User).filter(User.role == UserRole.MAINTAINER, User.is_active == True,
                                                     User.email.isnot(None)).all()
            to_emails = [m.email for m in maintainers if m.email]

            if not to_emails:
                raise HTTPException(status_code=400, detail="Nenhum mantenedor com e-mail cadastrado.")

            tz = ZoneInfo(settings.TIMEZONE)
            now = datetime.now(tz)
            now_local = now.replace(tzinfo=None)
            yesterday = now_local.date() - timedelta(days=1)

            full_report_html = daily_report_service.generate_daily_report_html(session, yesterday)
            fmt_start = yesterday.strftime(DATE_FORMAT)
            period_text = f"Abaixo está o relatório do dia {fmt_start}:"
        finally:
            if db is None and 'session' in locals():
                get_db_session().__exit__(None, None, None)

        backup_path = backup_service.create_safe_backup()
        if not backup_path:
            logger.exception('Backup - "Email manual" Error')
            raise HTTPException(status_code=400,
                                detail="Falha ao gerar a cópia de segurança do banco de dados local.")

        attachments = [(backup_path, "spe.db")]

        log_path = get_log_path(yesterday)
        if os.path.exists(log_path):
            attachments.append((log_path, f"log_{yesterday.strftime('%d%m%Y')}.log"))

        success = email_service.send_email(to_emails, attachments, full_report_html, period_text)

        if os.path.exists(backup_path):
            os.remove(backup_path)

        if success:
            return True
        else:
            logger.exception('Backup - "Email manual" Error')
            raise HTTPException(status_code=400, detail="Falha na conexão SMTP ao tentar enviar o email.")


routine_orchestrator = RoutineOrchestrator()
