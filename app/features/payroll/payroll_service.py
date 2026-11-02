import asyncio
import inspect
import logging
import os
import pathlib
import uuid
from datetime import date, datetime
from io import BytesIO
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.errors import constraint_name
from app.database.payroll_lock import lock_payroll_periods
from app.database.unit_of_work import transactional, unit_of_work
from app.features.payroll.payroll_exceptions import (
    PayrollAlreadyClosedError,
    PayrollClosureNotFoundError,
    PayrollInvalidPeriodError,
    PayrollNotClosedError,
    PayrollPeriodClosedError,
    PayrollPermissionError,
    PayrollReportGenerationError,
)
from app.features.payroll.payroll_models import PayrollClosure
from app.features.payroll.payroll_repository import (
    AsyncPayrollRepository,
    async_payroll_repository,
    payroll_repository,
)
from app.features.payroll.payroll_schemas import PayrollClosureResponse
from app.features.reports.excel_service import excel_service
from app.features.system.audit_service import audit_service
from app.features.system.email_service import email_service
from app.features.system.job_queue import enqueue
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import UserRole
from app.shared.storage import resolve_stored_file
from app.shared.upload_storage import UploadCategory, upload_storage

logger = logging.getLogger(__name__)


def dispatch_closure_email_background(month: int, year: int, user_name: str, report_path: str, to_emails: list[str]):
    try:
        full_path = os.path.join(settings.UPLOAD_DIR, report_path)
        attachment = None
        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                attachment = BytesIO(f.read())

        email_service.send_payroll_email(
            action="Fechamento", user_name=user_name, month=month, year=year, attachment=attachment, to_emails=to_emails
        )
    except Exception as e:
        logger.exception(f'Error in dispatch_closure_email_background: {type(e).__name__}')


class PayrollService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None,
            repo: Annotated[AsyncPayrollRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncPayrollRepository:
        return self._repo if self._repo is not None else async_payroll_repository

    async def _queue_notification(self, session, action: str, current_user, closure, month: int, year: int):
        maintainers = list((await session.scalars(select(User).where(
            User.role == UserRole.MAINTAINER, User.is_active.is_(True), User.email.isnot(None)
        ))).all())
        recipients = [maintainer.email for maintainer in maintainers if maintainer.email]
        await enqueue(session, 'NOTIFICATION', {
            'routine_type': 'EMAIL_PAYROLL', 'action': action, 'month': month, 'year': year,
            'user_name': current_user.name, 'to_emails': recipients,
            'report_path': closure.report_path if action == 'Fechamento' else None,
            'target_date': date(year, month, 1).isoformat(),
        }, f'EMAIL_PAYROLL:{closure.id}:{action}')

    def _build_history(self, month_closures: list) -> list[dict[str, Any]]:
        history = []
        for h in month_closures:
            history.append({
                "action": "Fechamento",
                "timestamp": h.closed_at,
                "user_id": h.closed_by_user_id,
                "user_name": h.closed_by.name if h.closed_by else None,
                "observation": None,
                "report_path": h.report_path
            })
            if h.deleted_at:
                history.append({
                    "action": "Reabertura",
                    "timestamp": h.deleted_at,
                    "user_id": h.deleted_by,
                    "user_name": h.deleter.name if h.deleter else None,
                    "observation": h.reopen_observation,
                    "report_path": None
                })
        history.sort(key=lambda x: x["timestamp"], reverse=True)
        return history

    def _build_period_response(self, mo: int, year: int, closures_by_month: dict) -> dict[str, Any]:
        history = []
        active_closure = None

        if mo in closures_by_month:
            month_closures = closures_by_month[mo]
            active_closure = next((c for c in month_closures if c.deleted_at is None), None)
            history = self._build_history(month_closures)

        if active_closure:
            return {
                "month": mo,
                "year": year,
                "is_closed": True,
                "id": active_closure.id,
                "closed_at": active_closure.closed_at,
                "closed_by_user_id": active_closure.closed_by_user_id,
                "closed_by_name": active_closure.closed_by.name if active_closure.closed_by else None,
                "history": history,
                "report_path": active_closure.report_path
            }
        else:
            return {
                "month": mo,
                "year": year,
                "is_closed": False,
                "id": None,
                "closed_at": None,
                "closed_by_user_id": None,
                "closed_by_name": None,
                "history": history,
                "report_path": None
            }

    async def list_periods(self, db: AsyncSession | None = None, year: int = 0) -> list[dict[str, Any]]:
        session = db if db is not None else self.db
        assert session is not None
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        current_year = now.year
        current_month = now.month

        if year < current_year:
            max_month = 12
        elif year == current_year:
            max_month = current_month
        else:
            max_month = 0

        stmt = select(PayrollClosure).where(PayrollClosure.year == year).order_by(PayrollClosure.id.asc())
        all_closures = list((await session.scalars(stmt)).all())

        closures_by_month = {}
        for c in all_closures:
            if c.month not in closures_by_month:
                closures_by_month[c.month] = []
            closures_by_month[c.month].append(c)

        result = []
        for mo in range(max_month, 0, -1):
            result.append(self._build_period_response(mo, year, closures_by_month))
        return result

    async def close_period(
            self,
            db: AsyncSession | None = None,
            month: int = 0,
            year: int = 0,
            current_user: User | None = None,
            background_tasks: BackgroundTasks | None = None,
            *,
            period: Any = None,
    ):
        if period is not None:
            month = period.month
            year = period.year
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        assert background_tasks is not None
        if current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
            raise PayrollPermissionError("Acesso negado: Sem permissão para fechar a folha.")

        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()

        request_date = date(year, month, 1)
        current_month_start = date(today.year, today.month, 1)

        if request_date >= current_month_start:
            raise PayrollInvalidPeriodError(
                f"Não é possível fechar a folha do mês atual ou de meses futuros ({month:02d}/{year}). Apenas meses anteriores podem ser fechados."
            )

        if isinstance(session, AsyncSession):
            await session.run_sync(lambda db: lock_payroll_periods(db, {(year, month)}, exclusive=True))
        existing = await self.repo.get_by_month(session, month, year)
        if existing:
            raise PayrollAlreadyClosedError(
                f"A folha de ponto referente a {month:02d}/{year} já está fechada."
            )

        try:
            res = excel_service.generate_excel_report(session, month, year, None, current_user)
            attachment = await res if inspect.isawaitable(res) else res

            reports_dir = os.path.join(settings.UPLOAD_DIR, "reports")
            os.makedirs(reports_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"folha_ponto_{month:02d}_{year}_{timestamp}.xlsx"
            file_path = os.path.join(reports_dir, filename)

            def _write_report():
                with open(file_path, "wb") as f:
                    f.write(attachment.getvalue())

            await asyncio.to_thread(_write_report)
        except Exception as e:
            logger.exception("Falha ao gerar/salvar arquivo do relatório de fechamento.")
            raise PayrollReportGenerationError(f"Falha ao gerar o relatório Excel: {e!s}")

        try:
            async with unit_of_work(session):
                closure = await self.repo.create(
                    session, month=month, year=year, user_id=current_user.id, commit=False
                )
                closure.report_path = f"reports/{filename}"
                await audit_service.async_log_change(session, current_user.id, "CLOSE", new_model=closure)
                await self._queue_notification(session, 'Fechamento', current_user, closure, month, year)
                response = PayrollClosureResponse.model_validate(closure)
                response.model_dump(mode="json")
        except IntegrityError as exc:
            await asyncio.to_thread(pathlib.Path(file_path).unlink, missing_ok=True)
            if constraint_name(exc) != "uq_payroll_closures_active_period":
                raise
            raise PayrollAlreadyClosedError(
                f"A folha de ponto referente a {month:02d}/{year} já está fechada."
            ) from exc
        except BaseException:
            await asyncio.to_thread(pathlib.Path(file_path).unlink, missing_ok=True)
            raise
        return response

    @transactional
    async def reopen_period(
            self,
            db: AsyncSession | None = None,
            month: int = 0,
            year: int = 0,
            observation: str = "",
            current_user: User | None = None,
            background_tasks: BackgroundTasks | None = None,
            *,
            period: Any = None,
    ):
        if period is not None:
            month = period.month
            year = period.year
            observation = period.observation
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        assert background_tasks is not None
        if current_user.role != UserRole.MAINTAINER:
            raise PayrollPermissionError("Acesso negado: Apenas mantenedores reabrem folhas.")

        if isinstance(session, AsyncSession):
            await session.run_sync(lambda db: lock_payroll_periods(db, {(year, month)}, exclusive=True))
        existing = await self.repo.get_by_month(session, month, year)
        if not existing:
            raise PayrollNotClosedError(
                f"A folha de ponto referente a {month:02d}/{year} não está fechada."
            )

        closure_id = existing.id
        await self.repo.delete(session, month, year, current_user.id, observation)

        await audit_service.async_log_change(
            session, current_user.id, "REOPEN",
            entity="PAYROLL_CLOSURE", entity_id=closure_id,
            old_data={"is_closed": True}, new_data={"is_closed": False}
        )

        await self._queue_notification(session, 'Reabertura', current_user, existing, month, year)
        return {"status": "success", "message": f"Folha de ponto de {month:02d}/{year} reaberta com sucesso."}

    def validate_period_open(self, db: Session | None = None, target_date: date | None = None):
        session = db if db is not None else self.db
        assert session is not None
        assert target_date is not None
        closure = payroll_repository.get_by_month(session, target_date.month, target_date.year)
        if closure:
            raise PayrollPeriodClosedError(
                f"A folha de ponto {target_date.month:02d}/{target_date.year} já está fechada."
            )

    async def async_validate_period_open(self, db: Any = None, target_date: date | None = None):
        session = db if db is not None else self.db
        assert session is not None
        assert target_date is not None
        closure = await async_payroll_repository.get_by_month(session, target_date.month, target_date.year)
        if closure:
            raise PayrollPeriodClosedError(
                f"A folha de ponto {target_date.month:02d}/{target_date.year} já está fechada."
            )

    async def upload_legacy_report(
            self,
            db: AsyncSession | None = None,
            closure_id: int = 0,
            original_filename: str = "",
            file_content: bytes = b"",
            upload_file: Any = None,
    ) -> dict[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        stmt = select(PayrollClosure).where(PayrollClosure.id == closure_id)
        closure = (await session.scalars(stmt)).first()
        if not closure:
            raise PayrollClosureNotFoundError(period=f"ID {closure_id}")

        if upload_file is not None:
            original_filename = upload_file.filename or ""
        extension = pathlib.Path(original_filename).suffix.lower()
        filename = f"folha_ponto_{closure.month:02d}_{closure.year}_{uuid.uuid4().hex}{extension}"
        if upload_file is not None:
            stored = await upload_storage.save(upload_file, UploadCategory.LEGACY_REPORT, filename)
        else:
            stored = await upload_storage.save_bytes(file_content, original_filename, UploadCategory.LEGACY_REPORT,
                                                     filename)
        closure.report_path = stored.relative_path
        try:
            await session.commit()
        except BaseException:
            await session.rollback()
            await upload_storage.remove(stored)
            raise
        return {"status": "success", "message": "Documento legado anexado com sucesso."}

    async def get_report_file_path(
            self,
            db: AsyncSession | None = None,
            closure_id: int = 0,
    ) -> tuple[str, str]:
        session = db if db is not None else self.db
        assert session is not None
        stmt = select(PayrollClosure).where(PayrollClosure.id == closure_id)
        closure = (await session.scalars(stmt)).first()
        if not closure or not closure.report_path:
            raise PayrollClosureNotFoundError(period=f"ID {closure_id}")

        file_path = resolve_stored_file(closure.report_path, 'reports')
        if file_path is None:
            raise PayrollClosureNotFoundError(period=f"ID {closure_id}")

        filename = os.path.basename(file_path)
        return str(file_path), filename


payroll_service = PayrollService()
