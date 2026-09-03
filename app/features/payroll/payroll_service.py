import asyncio
import inspect
import logging
import os
import pathlib
from datetime import date, datetime
from io import BytesIO
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
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
from app.features.reports.excel_service import excel_service
from app.features.system.audit_service import audit_service
from app.features.system.email_service import dispatch_payroll_email, email_service
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import UserRole

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
        logger.exception(f"Error in dispatch_closure_email_background: {e}")


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
    ):
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

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"folha_ponto_{month:02d}_{year}_{timestamp}.xlsx"
            file_path = os.path.join(reports_dir, filename)

            def _write_report():
                with open(file_path, "wb") as f:
                    f.write(attachment.getvalue())

            await asyncio.to_thread(_write_report)
        except Exception as e:
            logger.exception("Falha ao gerar/salvar arquivo do relatório de fechamento.")
            raise PayrollReportGenerationError(f"Falha ao gerar o relatório Excel: {str(e)}")

        await session.commit()

        closure = await self.repo.create(session, month=month, year=year, user_id=current_user.id)
        closure.report_path = f"reports/{filename}"
        await session.commit()
        await session.refresh(closure)

        await audit_service.async_log_change(session, current_user.id, "CLOSE", new_model=closure)

        stmt = select(User).where(
            User.role == UserRole.MAINTAINER,
            User.is_active == True,
            User.email.isnot(None),
        )
        maintainers = list((await session.scalars(stmt)).all())
        to_emails = [m.email for m in maintainers if m.email]

        background_tasks.add_task(
            dispatch_closure_email_background,
            month, year, current_user.name, closure.report_path, to_emails
        )
        return closure

    async def reopen_period(
            self,
            db: AsyncSession | None = None,
            month: int = 0,
            year: int = 0,
            observation: str = "",
            current_user: User | None = None,
            background_tasks: BackgroundTasks | None = None,
    ):
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        assert background_tasks is not None
        if current_user.role != UserRole.MAINTAINER:
            raise PayrollPermissionError("Acesso negado: Apenas mantenedores reabrem folhas.")

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

        stmt = select(User).where(
            User.role == UserRole.MAINTAINER,
            User.is_active == True,
            User.email.isnot(None),
        )
        maintainers = list((await session.scalars(stmt)).all())
        to_emails = [m.email for m in maintainers if m.email]

        background_tasks.add_task(
            dispatch_payroll_email,
            "Reabertura", current_user.name, month, year, to_emails
        )
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
    ):
        session = db if db is not None else self.db
        assert session is not None
        stmt = select(PayrollClosure).where(PayrollClosure.id == closure_id)
        closure = (await session.scalars(stmt)).first()
        if not closure:
            raise PayrollClosureNotFoundError(period=f"ID {closure_id}")

        legacy_dir = os.path.join(settings.UPLOAD_DIR, "reports", "legacy")
        os.makedirs(legacy_dir, exist_ok=True)

        ext = pathlib.Path(original_filename).suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"folha_ponto_{closure.month:02d}_{closure.year}_{timestamp}{ext}"
        file_path = os.path.join(legacy_dir, filename)

        def _write_legacy():
            with open(file_path, "wb") as f:
                f.write(file_content)

        await asyncio.to_thread(_write_legacy)

        closure.report_path = f"reports/legacy/{filename}"
        await session.commit()


payroll_service = PayrollService()
