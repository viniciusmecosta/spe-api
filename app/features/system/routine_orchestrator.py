import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import is_dev, is_prod, settings
from app.core.logger import get_log_path
from app.database.session import get_async_session_context
from app.features.reports.daily_report_service import daily_report_service
from app.features.system.backup_service import backup_service
from app.features.system.job_queue import submit
from app.features.system.system_exceptions import (
    NoMaintainersWithEmailError,
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
BACKUP_DB_FILENAME = "spe-db.sql"
BACKUP_SQL_FILENAME = "spe_dump.sql"
BACKUP_ZIP_FILENAME = "spe.zip"
ENCRYPTED_BACKUP_FILENAME = "spe.zip.enc"


class RoutineOrchestrator:
    def __init__(
            self,
            db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None,
            repo: Annotated[AsyncRoutineLogRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    async def _enqueue_routine(self, routine_type: str, scheduled: bool = False,
                               start_date: date | None = None, end_date: date | None = None):
        now = datetime.now(ZoneInfo(settings.TIMEZONE))
        if scheduled and not self._schedule_allows_run(routine_type, now):
            return None
        end_date = end_date or now.date() - timedelta(days=1)
        start_date = start_date or end_date
        if scheduled and await self._already_delivered(routine_type, now, end_date):
            return None
        target = now.strftime('%Y-%m-%dT%H') if 'HOURLY' in routine_type else end_date.isoformat()
        key = f'{routine_type}:{target}' if scheduled else None
        return await submit('NOTIFICATION', {
            'routine_type': routine_type, 'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(), 'target_date': end_date.isoformat(),
        }, key)

    async def _already_delivered(self, routine_type: str, now: datetime, target_date: date) -> bool:
        async with get_async_session_context() as session:
            if 'HOURLY' in routine_type:
                start = now.replace(minute=0, second=0, microsecond=0)
                return await self.repo.has_hourly_routine_run(session, routine_type, start, status='SUCCESS')
            return await self.repo.has_routine_run_for_target_date(
                session, routine_type, target_date, status='SUCCESS',
            )

    @staticmethod
    def _schedule_allows_run(routine_type: str, now: datetime) -> bool:
        if routine_type == 'TELEGRAM_DAILY_REPORT':
            return not is_dev() and now.hour >= settings.DAILY_REPORT_HOUR
        if not is_prod():
            return False
        if 'HOURLY' in routine_type:
            return settings.HOURLY_BACKUP_START_HOUR <= now.hour <= settings.HOURLY_BACKUP_END_HOUR
        return now.hour >= settings.DAILY_REPORT_HOUR

    @property
    def repo(self) -> AsyncRoutineLogRepository:
        return self._repo if self._repo is not None else async_routine_log_repository

    def _resolve_backup_filename(self, zip_path: str | None, backup_path: str | None) -> str:
        if zip_path:
            return ENCRYPTED_BACKUP_FILENAME if zip_path.endswith(".enc") else BACKUP_ZIP_FILENAME
        if backup_path:
            return BACKUP_DB_FILENAME
        return BACKUP_SQL_FILENAME

    def _generate_backup_files_zip_sync(self) -> tuple[str | None, str | None, str | None]:
        backup_path = sql_path = zip_path = None
        try:
            with backup_service.consistent_snapshot():
                backup_path = backup_service.create_safe_backup()
                sql_path = backup_service.create_sql_dump()
            if not backup_path or not sql_path:
                raise RuntimeError("Schema ou dados não foram gerados")
            zip_path = backup_service.compress_files(
                {backup_path: BACKUP_DB_FILENAME, sql_path: BACKUP_SQL_FILENAME},
                backup_path + '.zip',
            )
            if not zip_path or not zip_path.endswith(".enc"):
                raise RuntimeError("Pacote criptografado não foi gerado")
            return backup_path, sql_path, zip_path
        except Exception:
            logger.exception("Falha ao gerar backup consistente e criptografado")
            self._cleanup_backup_files_sync(backup_path, sql_path, zip_path)
            return None, None, None

    async def _generate_backup_files_zip(self) -> tuple[str | None, str | None, str | None]:
        return await asyncio.to_thread(self._generate_backup_files_zip_sync)

    def _cleanup_backup_files_sync(self, backup_path, sql_path, zip_path):
        for p in set(filter(None, [backup_path, sql_path, zip_path])):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError as e:
                    logger.error(f"Erro ao remover arquivo temporario {p}: {type(e).__name__} - {e}",
                                     exc_info=False)

    async def _cleanup_backup_files(self, backup_path, sql_path, zip_path):
        await asyncio.to_thread(self._cleanup_backup_files_sync, backup_path, sql_path, zip_path)

    async def execute_hourly_backup_telegram(self):
        return await self._enqueue_routine('TELEGRAM_HOURLY_BACKUP', scheduled=True)

    async def send_managerial_report_telegram(self):
        return await self._enqueue_routine('TELEGRAM_DAILY_REPORT', scheduled=True)

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

    def _prepare_backup_attachments(
        self,
        attachments: list[tuple[str, str]],
        zip_path: str | None,
    ) -> None:
        if zip_path and zip_path.endswith(".enc") and os.path.exists(zip_path):
            attachments.insert(0, (zip_path, ENCRYPTED_BACKUP_FILENAME))

    async def _log_daily_backup_email_execution(
        self, success: bool, yesterday: date, now_local: datetime
    ) -> None:
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
            logger.error(
                f'Erro de banco ao salvar log de backup diário por email: {type(e).__name__} - {e}',
                exc_info=False,
            )

    async def run_daily_backup_routine_email(self):
        return await self._enqueue_routine('EMAIL_DAILY_BACKUP', scheduled=True)

    async def clean_old_logs(self, days_to_keep: int | None = None):
        if is_dev():
            return
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
            logger.error(f"Erro de banco ao verificar rotina de limpeza: {type(e).__name__} - {e}", exc_info=False)
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
            logger.error(f"Erro de banco ao limpar routine_logs: {type(e).__name__} - {e}", exc_info=False)

    async def _send_system_logs_telegram(self, yesterday: date, today: date):
        for log_date in [yesterday, today]:
            log_path = get_log_path(log_date)
            if await asyncio.to_thread(os.path.exists, log_path):
                await asyncio.to_thread(
                    telegram_service.send_document,
                    log_path,
                    f"Log do sistema - {log_date.strftime(DATE_FORMAT)}",
                    filename=f"log_{log_date.strftime('%d%m%Y')}.log",
                )

    async def execute_manual_backup_telegram(self):
        return await self._enqueue_routine('TELEGRAM_MANUAL_BACKUP')

    async def send_manual_report_telegram(self, start_date, end_date):
        return await self._enqueue_routine('TELEGRAM_MANUAL_REPORT', start_date=start_date, end_date=end_date)

    async def _fetch_manual_backup_report(self, session: AsyncSession) -> tuple[list[str], str, str, date, date]:
        stmt = select(User).where(User.role == UserRole.MAINTAINER, User.is_active == True, User.email.isnot(None))
        res = await session.scalars(stmt)
        maintainers = res.all()
        to_emails = [m.email for m in maintainers if m.email]
        if not to_emails:
            raise NoMaintainersWithEmailError()

        tz = ZoneInfo(settings.TIMEZONE)
        now_local = datetime.now(tz).replace(tzinfo=None)
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        full_report_html = await daily_report_service.generate_daily_report_html(session, yesterday)
        period_text = f"Abaixo está o relatório do dia {yesterday.strftime(DATE_FORMAT)}:"
        return to_emails, full_report_html, period_text, yesterday, today

    async def _build_email_attachments(
        self,
        backup_file: str,
        yesterday: date,
        today: date,
    ) -> list[tuple[str, str]]:
        filename = ENCRYPTED_BACKUP_FILENAME if backup_file.endswith(".enc") else BACKUP_ZIP_FILENAME
        attachments = [(backup_file, filename)]
        for log_date in [yesterday, today]:
            log_path = get_log_path(log_date)
            if await asyncio.to_thread(os.path.exists, log_path):
                attachments.append((log_path, f"log_{log_date.strftime('%d%m%Y')}.log"))
        return attachments

    async def send_manual_backup_email(self) -> int:
        return await self._enqueue_routine('EMAIL_MANUAL_BACKUP')

    async def trigger_manual_backup_email(
            self,
            current_user: User,
            audit_svc: Any,
    ) -> dict[str, str]:
        job_id = await self.send_manual_backup_email()
        await audit_svc.async_log(user_id=current_user.id, action="MANUAL_BACKUP_EMAIL", entity="SYSTEM", entity_id=0)
        return {"status": "success", "job_id": str(job_id), "message": "Backup manual por e-mail registrado para processamento em segundo plano."}

    async def trigger_manual_backup_telegram(
            self,
            current_user: User,
            audit_svc: Any,
    ) -> dict[str, str]:
        job_id = await self.execute_manual_backup_telegram()
        await audit_svc.async_log(user_id=current_user.id, action="MANUAL_BACKUP_TELEGRAM", entity="SYSTEM",
                                  entity_id=0)
        return {"job_id": str(job_id), "message": "Backup manual registrado para processamento no Telegram."}

    async def trigger_manual_report_telegram(
            self,
            start_date: date,
            end_date: date,
            current_user: User,
            audit_svc: Any,
            telegram_svc: Any,
    ) -> dict[str, str]:
        telegram_svc.validate_manual_report_dates(start_date, end_date)
        job_id = await self.send_manual_report_telegram(start_date, end_date)
        await audit_svc.async_log(
            user_id=current_user.id,
            action="MANUAL_REPORT_TELEGRAM",
            entity="SYSTEM",
            entity_id=0,
            new_data={"start_date": str(start_date), "end_date": str(end_date)},
        )
        return {
            "job_id": str(job_id),
            "message": f"Relatório do período {start_date} até {end_date} enviado para processamento em background."
        }


routine_orchestrator = RoutineOrchestrator()
