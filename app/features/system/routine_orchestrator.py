import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_log_path
from app.database.session import get_async_session_context
from app.features.reports.daily_report_service import daily_report_service
from app.features.system.backup_service import backup_service
from app.features.system.email_service import email_service
from app.features.system.system_exceptions import (
    BackupGenerationFailedError,
    EmailNotConfiguredError,
    NoMaintainersWithEmailError,
    SMTPConnectionFailedError,
)
from app.features.system.system_repository import (
    AsyncRoutineLogRepository,
    async_routine_log_repository,
)
from app.features.system.telegram_service import telegram_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import UserRole

logger = logging.getLogger(__name__)
DATE_FORMAT = "%d/%m/%Y"
BACKUP_DB_FILENAME = "spe.db"
BACKUP_SQL_FILENAME = "spe_dump.sql"
BACKUP_ZIP_FILENAME = "spe.zip"


class RoutineOrchestrator:
    def __init__(
            self,
            db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None,
            repo: Annotated[AsyncRoutineLogRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncRoutineLogRepository:
        return self._repo if self._repo is not None else async_routine_log_repository

    def _generate_backup_files_zip_sync(self) -> tuple[str | None, str | None, str | None]:
        backup_path = backup_service.create_safe_backup()
        if not backup_path:
            return None, None, None
        sql_path = backup_service.create_sql_dump(backup_path)
        files_to_compress = {backup_path: BACKUP_DB_FILENAME}
        if sql_path:
            files_to_compress[sql_path] = BACKUP_SQL_FILENAME
        zip_path = backup_service.compress_files(files_to_compress, backup_path + '.zip')
        return backup_path, sql_path, zip_path

    async def _generate_backup_files_zip(self) -> tuple[str | None, str | None, str | None]:
        return await asyncio.to_thread(self._generate_backup_files_zip_sync)

    def _cleanup_backup_files_sync(self, backup_path, sql_path, zip_path):
        for p in [backup_path, sql_path, zip_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError as e:
                    logger.exception(f"Erro ao remover arquivo temporario {p}: {type(e).__name__} - {e}",
                                     exc_info=False)

    async def _cleanup_backup_files(self, backup_path, sql_path, zip_path):
        await asyncio.to_thread(self._cleanup_backup_files_sync, backup_path, sql_path, zip_path)

    async def execute_hourly_backup_telegram(self):
        if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
            return

        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)

        if now_local.hour < settings.HOURLY_BACKUP_START_HOUR or now_local.hour > settings.HOURLY_BACKUP_END_HOUR:
            return

        try:
            async with get_async_session_context() as db_read:
                current_hour_start_local = now_local.replace(minute=0, second=0, microsecond=0)
                if await self.repo.has_hourly_routine_run(db_read, "TELEGRAM_HOURLY_BACKUP", current_hour_start_local,
                                                          status="SUCCESS"):
                    return
        except SQLAlchemyError as e:
            logger.exception(f"Erro de banco ao verificar backup horário Telegram: {type(e).__name__} - {e}",
                             exc_info=False)
            return

        backup_path, sql_path, zip_path = await self._generate_backup_files_zip()
        if not backup_path:
            logger.error('Backup - "Telegram horário" Error')
            return

        now_str = now_local.strftime('%H:%M')
        caption = f"[Backup Automático] - {now_str}"

        try:
            success = await asyncio.to_thread(
                telegram_service.send_document,
                zip_path or backup_path,
                caption,
                filename=BACKUP_ZIP_FILENAME if zip_path else BACKUP_DB_FILENAME
            )

            try:
                async with get_async_session_context() as db_write:
                    if success:
                        await self.repo.log_execution(
                            db_write,
                            routine_type="TELEGRAM_HOURLY_BACKUP",
                            status="SUCCESS",
                            execution_time=now_local,
                        )
                    else:
                        logger.error('Backup - "Telegram horário" Error')
            except SQLAlchemyError as e:
                logger.exception(
                    f'Erro de banco ao salvar log de execução do backup horário Telegram: {type(e).__name__} - {e}',
                    exc_info=False)
        finally:
            await self._cleanup_backup_files(backup_path, sql_path, zip_path)

    async def send_managerial_report_telegram(self):
        if settings.ENVIRONMENT and settings.ENVIRONMENT.lower() == "dev":
            return

        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        if now_local.hour < settings.DAILY_REPORT_HOUR:
            return

        try:
            async with get_async_session_context() as db_read:
                if await self.repo.has_routine_run_for_target_date(db_read, "TELEGRAM_DAILY_REPORT", yesterday,
                                                                   status="SUCCESS"):
                    return

                last_success = await self.repo.get_last_successful_target_date(db_read, "TELEGRAM_DAILY_REPORT")
                start_date = (last_success + timedelta(days=1)) if last_success else yesterday
                start_date = min(start_date, yesterday)

                report_text = await telegram_service.generate_report_text(
                    db_read, start_date, yesterday
                )
        except SQLAlchemyError as e:
            logger.exception(f"Erro de banco ao gerar report gerencial Telegram: {type(e).__name__} - {e}",
                             exc_info=False)
            return

        text_success = await asyncio.to_thread(telegram_service.send_text, report_text)

        current_log_date = start_date
        while current_log_date <= yesterday:
            log_path = get_log_path(current_log_date)
            if await asyncio.to_thread(os.path.exists, log_path):
                await asyncio.to_thread(
                    telegram_service.send_document,
                    log_path,
                    f"Logs do sistema - {current_log_date.strftime(DATE_FORMAT)}"
                )
            current_log_date += timedelta(days=1)

        try:
            async with get_async_session_context() as db_write:
                await self.repo.log_execution(
                    db_write,
                    routine_type="TELEGRAM_DAILY_REPORT",
                    target_date=yesterday,
                    status="SUCCESS" if text_success else "FAILED",
                    execution_time=now_local,
                )
                if not text_success:
                    logger.error('Relatório - "Telegram diário" Error')
        except SQLAlchemyError as e:
            logger.exception(f'Erro de banco ao salvar log do relatório diário Telegram: {type(e).__name__} - {e}',
                             exc_info=False)

    async def _generate_daily_backup_report(self, db_read, start_date, yesterday):
        full_report_html = ""
        attachments = []
        current_check_date = start_date
        while current_check_date <= yesterday:
            daily_html = await daily_report_service.generate_daily_report_html(db_read, current_check_date)
            full_report_html += daily_html
            log_path = get_log_path(current_check_date)
            if await asyncio.to_thread(os.path.exists, log_path):
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

    async def run_daily_backup_routine_email(self):
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        if now_local.hour < settings.DAILY_REPORT_HOUR:
            return

        try:
            async with get_async_session_context() as db_read:
                if await self.repo.has_routine_run_for_target_date(db_read, "EMAIL_DAILY_BACKUP", yesterday,
                                                                   status="SUCCESS"):
                    return

                stmt = select(User).where(User.role == UserRole.MAINTAINER, User.is_active == True,
                                          User.email.isnot(None))
                res = await db_read.scalars(stmt)
                maintainers = res.all()
                to_emails = [m.email for m in maintainers if m.email]

                if not to_emails:
                    return

                last_success = await self.repo.get_last_successful_target_date(db_read, "EMAIL_DAILY_BACKUP")
                start_date = (last_success + timedelta(days=1)) if last_success else yesterday
                start_date = min(start_date, yesterday)

                full_report_html, attachments, period_text = await self._generate_daily_backup_report(db_read,
                                                                                                      start_date,
                                                                                                      yesterday)
        except SQLAlchemyError as e:
            logger.exception(f"Erro de banco ao checar backup diário por email: {type(e).__name__} - {e}",
                             exc_info=False)
            return

        backup_path, sql_path, zip_path = await self._generate_backup_files_zip()
        if not backup_path:
            logger.error('Backup - "Email diário" Error')
            return

        attachments.insert(0, (zip_path or backup_path, BACKUP_ZIP_FILENAME if zip_path else BACKUP_DB_FILENAME))

        try:
            success = await asyncio.to_thread(email_service.send_email, to_emails, attachments, full_report_html,
                                              period_text)

            try:
                async with get_async_session_context() as db_write:
                    await self.repo.log_execution(
                        db_write,
                        routine_type="EMAIL_DAILY_BACKUP",
                        target_date=yesterday,
                        status="SUCCESS" if success else "FAILED",
                        execution_time=now_local,
                    )
                    if not success:
                        logger.error('Backup - "Email diário" Error')
            except SQLAlchemyError as e:
                logger.exception(f'Erro de banco ao salvar log de backup diário por email: {type(e).__name__} - {e}',
                                 exc_info=False)
        finally:
            await self._cleanup_backup_files(backup_path, sql_path, zip_path)

    async def clean_old_logs(self, days_to_keep: int = None):
        days_to_keep = days_to_keep or settings.ROUTINE_LOG_RETENTION_DAYS
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        today = now_local.date()

        try:
            async with get_async_session_context() as db_read:
                if await self.repo.has_routine_run_for_target_date(db_read, "CLEANUP_ROUTINE_LOGS", today,
                                                                   status="SUCCESS"):
                    return
        except SQLAlchemyError as e:
            logger.exception(f"Erro de banco ao verificar rotina de limpeza: {type(e).__name__} - {e}", exc_info=False)
            return

        try:
            async with get_async_session_context() as db_write:
                cutoff_date = now_local - timedelta(days=days_to_keep)
                deleted_count = await self.repo.delete_older_than(db_write, cutoff_date)

                await self.repo.log_execution(
                    db_write,
                    routine_type="CLEANUP_ROUTINE_LOGS",
                    target_date=today,
                    status="SUCCESS",
                    execution_time=now_local,
                    details=f"{deleted_count} logs apagados",
                )
        except SQLAlchemyError as e:
            logger.exception(f"Erro de banco ao limpar routine_logs: {type(e).__name__} - {e}", exc_info=False)

    async def execute_manual_backup_telegram(self):
        backup_path, sql_path, zip_path = await self._generate_backup_files_zip()
        if not backup_path:
            logger.error('Backup - "Telegram manual" Error')
            return

        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        now_local = now.replace(tzinfo=None)
        now_str = now_local.strftime('%d/%m/%Y %H:%M')
        caption = f"[Backup Manual Solicitado] - {now_str}"

        try:
            success = await asyncio.to_thread(
                telegram_service.send_document,
                zip_path or backup_path,
                caption,
                filename=BACKUP_ZIP_FILENAME if zip_path else BACKUP_DB_FILENAME
            )

            try:
                async with get_async_session_context() as db_write:
                    await self.repo.log_execution(
                        db_write,
                        routine_type="TELEGRAM_MANUAL_BACKUP",
                        status="SUCCESS" if success else "FAILED",
                        execution_time=now_local,
                    )
                    if not success:
                        logger.error('Backup - "Telegram manual" Error')
            except SQLAlchemyError as e:
                logger.exception(f"Erro de banco ao salvar rotina manual: {type(e).__name__} - {e}", exc_info=False)
        finally:
            await self._cleanup_backup_files(backup_path, sql_path, zip_path)

    async def send_manual_report_telegram(self, start_date, end_date):
        tz = ZoneInfo(settings.TIMEZONE)
        now_local = datetime.now(tz).replace(tzinfo=None)

        try:
            async with get_async_session_context() as db_read:
                report_text = await telegram_service.generate_report_text(
                    db_read, start_date, end_date, "Relatório Gerencial Manual -"
                )
        except SQLAlchemyError as e:
            logger.exception(f"Erro de banco ao buscar report manual: {type(e).__name__} - {e}", exc_info=False)
            return

        text_success = await asyncio.to_thread(telegram_service.send_text, report_text)

        current_log_date = start_date
        while current_log_date <= end_date:
            log_path = get_log_path(current_log_date)
            if await asyncio.to_thread(os.path.exists, log_path):
                await asyncio.to_thread(
                    telegram_service.send_document,
                    log_path,
                    f"Logs do sistema - {current_log_date.strftime(DATE_FORMAT)}"
                )
            current_log_date += timedelta(days=1)

        try:
            async with get_async_session_context() as db_write:
                await self.repo.log_execution(
                    db_write,
                    routine_type="TELEGRAM_MANUAL_REPORT",
                    target_date=end_date,
                    status="SUCCESS" if text_success else "FAILED",
                    execution_time=now_local,
                )

                if not text_success:
                    logger.error('Relatório - "Telegram manual" Error')
        except SQLAlchemyError as e:
            logger.exception(f"Erro de banco ao salvar rotina de relatorio manual: {type(e).__name__} - {e}",
                             exc_info=False)

    async def send_manual_backup_email(self, db: AsyncSession | None = None) -> bool:
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            raise EmailNotConfiguredError()

        session = db if db is not None else self.db
        if session is not None:
            stmt = select(User).where(User.role == UserRole.MAINTAINER, User.is_active == True, User.email.isnot(None))
            res = await session.scalars(stmt)
            maintainers = res.all()
            to_emails = [m.email for m in maintainers if m.email]

            if not to_emails:
                raise NoMaintainersWithEmailError()

            tz = ZoneInfo(settings.TIMEZONE)
            now = datetime.now(tz)
            now_local = now.replace(tzinfo=None)
            yesterday = now_local.date() - timedelta(days=1)

            full_report_html = await daily_report_service.generate_daily_report_html(session, yesterday)
            fmt_start = yesterday.strftime(DATE_FORMAT)
            period_text = f"Abaixo está o relatório do dia {fmt_start}:"
        else:
            async with get_async_session_context() as bg_session:
                stmt = select(User).where(User.role == UserRole.MAINTAINER, User.is_active == True,
                                          User.email.isnot(None))
                res = await bg_session.scalars(stmt)
                maintainers = res.all()
                to_emails = [m.email for m in maintainers if m.email]

                if not to_emails:
                    raise NoMaintainersWithEmailError()

                tz = ZoneInfo(settings.TIMEZONE)
                now = datetime.now(tz)
                now_local = now.replace(tzinfo=None)
                yesterday = now_local.date() - timedelta(days=1)

                full_report_html = await daily_report_service.generate_daily_report_html(bg_session, yesterday)
                fmt_start = yesterday.strftime(DATE_FORMAT)
                period_text = f"Abaixo está o relatório do dia {fmt_start}:"

        backup_path, sql_path, zip_path = await self._generate_backup_files_zip()
        if not backup_path:
            logger.error('Backup - "Email manual" Error')
            raise BackupGenerationFailedError()

        attachments = [(zip_path or backup_path, BACKUP_ZIP_FILENAME if zip_path else BACKUP_DB_FILENAME)]

        log_path = get_log_path(yesterday)
        if await asyncio.to_thread(os.path.exists, log_path):
            attachments.append((log_path, f"log_{yesterday.strftime('%d%m%Y')}.log"))

        try:
            success = await asyncio.to_thread(email_service.send_email, to_emails, attachments, full_report_html,
                                              period_text)
        finally:
            await self._cleanup_backup_files(backup_path, sql_path, zip_path)

        if success:
            return True
        else:
            logger.error('Backup - "Email manual" Error')
            raise SMTPConnectionFailedError()


routine_orchestrator = RoutineOrchestrator()
