import io
import json
import logging
import zipfile
from calendar import monthrange
from datetime import date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DomainException
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.companies.company_repository import (
    async_company_repository,
    company_repository,
)
from app.features.daily_summaries.daily_summary_service import daily_summary_service
from app.features.holidays.holiday_repository import (
    async_holiday_repository,
    holiday_repository,
)
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_repository import (
    async_time_record_repository,
    time_record_repository,
)
from app.features.timesheets.timesheet_exceptions import (
    FutureTimesheetNotAllowedError,
    NoTimesheetRecordsFoundError,
    TimesheetExportFailedError,
    TimesheetUserNotFoundError,
)
from app.features.timesheets.timesheet_pdf_builder import TimesheetPdfBuilder
from app.features.users.user_models import User
from app.features.users.user_repository import (
    async_user_repository,
    user_repository,
)
from app.shared import deps
from app.shared.enums import UserRole

logger = logging.getLogger(__name__)


class TimesheetZip(io.BytesIO):
    def __init__(self):
        super().__init__()
        self.generated: list[dict[str, int | str]] = []
        self.failed: list[dict[str, int | str]] = []

    @property
    def export_headers(self) -> dict[str, str]:
        return {
            "X-Export-Status": "partial" if self.failed else "complete",
            "X-Export-Generated-Count": str(len(self.generated)),
            "X-Export-Failed-Count": str(len(self.failed)),
        }


class TimesheetService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db
        self.pdf_builder = TimesheetPdfBuilder()

    def validate_date_not_future(self, month: int, year: int) -> None:
        now = datetime.now()
        if year > now.year or (year == now.year and month > now.month):
            raise FutureTimesheetNotAllowedError()


    async def _fetch_user(self, session, user_id: int):
        if hasattr(session, "sync_session"):
            return await async_user_repository.get(session, user_id)
        return user_repository.get(session, user_id)

    async def _fetch_period_data(
        self, session, user_id: int, start_dt, end_dt, start_date, end_date, month: int, year: int
    ):
        if hasattr(session, "sync_session"):
            records = await async_time_record_repository.get_by_range(session, user_id, start_dt, end_dt)
            holidays = await async_holiday_repository.get_by_month(session, month, year)
            adj_stmt = select(AdjustmentRequest).where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None),
            )
            adj_res = await session.scalars(adj_stmt)
            all_adjustments = list(adj_res.all())
            company = await async_company_repository.get_current(session)
            return records, holidays, all_adjustments, company

        records = time_record_repository.get_by_range(session, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(session, month, year)
        all_adjustments = session.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.deleted_at.is_(None),
        ).all()
        company = company_repository.get_current(session)
        return records, holidays, all_adjustments, company


    async def generate_user_timesheet_pdf(
        self, db: Any | None = None, user_id: int = 0, month: int = 0, year: int = 0
    ) -> io.BytesIO:
        self.validate_date_not_future(month, year)
        session = db if db is not None else self.db
        assert session is not None
        user = await self._fetch_user(session, user_id)
        if not user:
            raise TimesheetUserNotFoundError(user_id=user_id)

        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)
        records, holidays, all_adjustments, company = await self._fetch_period_data(
            session, user_id, start_dt, end_dt, start_date, end_date, month, year
        )
        historical_schedules = user.historical_schedules if user else []
        period_result = await daily_summary_service.build_period(
            session, user_id, start_date, end_date,
            records, all_adjustments, holidays, historical_schedules,
        )
        return self.pdf_builder.build(
            user=user,
            company=company,
            month=month,
            year=year,
            start_date=start_date,
            end_date=end_date,
            today=today,
            records=records,
            holidays=holidays,
            all_adjustments=all_adjustments,
            period_result=period_result,
        )

    async def generate_all_timesheets_pdf_zip(self, db: Any | None = None, month: int = 0, year: int = 0,
                                        employee_ids: list[int] | None = None) -> TimesheetZip:
        self.validate_date_not_future(month, year)
        session = db if db is not None else self.db
        assert session is not None
        tz = ZoneInfo(settings.TIMEZONE)
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        if hasattr(session, "sync_session"):
            stmt = (
                select(User)
                .join(TimeRecord, User.id == TimeRecord.user_id)
                .where(
                    User.role == UserRole.EMPLOYEE,
                    User.is_exempt_from_rules.is_(False),
                    TimeRecord.record_datetime >= start_dt,
                    TimeRecord.record_datetime <= end_dt,
                    TimeRecord.is_ignored.is_(False),
                )
                .distinct()
            )
            if employee_ids:
                stmt = stmt.where(User.id.in_(employee_ids))
            res = await session.scalars(stmt)
            users = list(res.all())
        else:
            query = session.query(User).join(TimeRecord, User.id == TimeRecord.user_id).filter(
                User.role == UserRole.EMPLOYEE,
                User.is_exempt_from_rules.is_(False),
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored == False
            ).distinct()
            if employee_ids:
                query = query.filter(User.id.in_(employee_ids))
            users = query.all()

        if not users:
            raise NoTimesheetRecordsFoundError()

        zip_buffer = TimesheetZip()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            used_names: set[str] = set()
            for user in sorted(users, key=lambda item: (item.name.casefold(), item.id)):
                await self._add_timesheet_to_zip(session, user, month, year, zip_file, zip_buffer, used_names)
            if not zip_buffer.generated:
                raise TimesheetExportFailedError()
            if zip_buffer.failed:
                manifest = {
                    "status": "partial", "month": month, "year": year,
                    "generated": zip_buffer.generated, "failed": zip_buffer.failed,
                }
                zip_file.writestr('manifesto_exportacao.json', json.dumps(manifest, ensure_ascii=False, indent=2))

        zip_buffer.seek(0)
        return zip_buffer

    async def _add_timesheet_to_zip(self, session, user, month: int, year: int, zip_file: zipfile.ZipFile,
                                    result: TimesheetZip, used_names: set[str]) -> None:
        try:
            pdf_buffer = await self.generate_user_timesheet_pdf(session, user.id, month, year)
            content = pdf_buffer.getvalue()
            if not content:
                raise ValueError('Espelho de ponto vazio.')
            safe_name = "".join(c for c in user.name if c.isalnum() or c == ' ').rstrip().replace(" ", "_")
            filename = f"espelho_ponto_{safe_name}_{month:02d}_{year}.pdf"
            if filename in used_names:
                filename = f"espelho_ponto_{safe_name}_{user.id}_{month:02d}_{year}.pdf"
            zip_file.writestr(filename, content)
            used_names.add(filename)
            result.generated.append({"user_id": user.id, "user_name": user.name, "filename": filename})
        except (ValueError, OSError, RuntimeError, DomainException):
            logger.exception("Erro ao gerar espelho de ponto em lote (User %s)", user.id)
            result.failed.append({"user_id": user.id, "user_name": user.name,
                                  "detail": "Não foi possível gerar o espelho deste funcionário."})
