import os
import sys
from datetime import date, datetime
from io import BytesIO
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.companies.company_repository import (
    async_company_repository,
    company_repository,
)
from app.features.holidays.holiday_repository import (
    async_holiday_repository,
    holiday_repository,
)
from app.features.payroll.payroll_repository import async_payroll_repository
from app.features.reports.report_exceptions import EmployeeInvalidReportPeriodError
from app.features.reports.excel_workbook_builder import ExcelWorkbookBuilder
from app.features.reports.report_service import report_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import UserRole


class ExcelService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db
        self.workbook_builder = ExcelWorkbookBuilder()

    def _validate_employee_report_period(self, current_user: User, month: int, year: int):
        if not current_user:
            return
        if current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]:
            return

        now = sys.modules['datetime'].datetime.now()
        current_month = now.month
        current_year = now.year

        if current_month == 1:
            prev_month = 12
            prev_year = current_year - 1
        else:
            prev_month = current_month - 1
            prev_year = current_year

        if (year == current_year and month == current_month) or \
                (year == prev_year and month == prev_month):
            return

        raise EmployeeInvalidReportPeriodError(period=f"{month:02d}/{year}")

    async def _fetch_users_and_company(self, session: Any, employee_ids: list[int] | None):
        if hasattr(session, "sync_session"):
            stmt = select(User).options(selectinload(User.historical_schedules))
            stmt = report_service.apply_employee_filters(stmt, employee_ids)
            res = await session.scalars(stmt)
            users = list(res.all())
            company = await async_company_repository.get_current(session)
        else:
            query = session.query(User).options(joinedload(User.historical_schedules))
            query = report_service.apply_employee_filters(query, employee_ids)
            users = query.all()
            company = company_repository.get_current(session)
        return users, company

    def _resolve_logo_path(self, company) -> str | None:
        if company and company.logo_path:
            full_logo_path = os.path.join(settings.UPLOAD_DIR, "public", company.logo_path)
            if os.path.exists(full_logo_path):
                return full_logo_path
            legacy_path = os.path.join(settings.UPLOAD_DIR, company.logo_path)
            if os.path.exists(legacy_path):
                return legacy_path
        return None

    async def _fetch_batch_data(self, session: Any, user_ids: list[int], start_dt: datetime, end_dt: datetime,
                                start_date: date, end_date: date, month: int, year: int):
        if hasattr(session, "sync_session"):
            if not user_ids:
                return [], [], await async_holiday_repository.get_by_month(session, month, year)
            rec_stmt = select(TimeRecord).options(selectinload(TimeRecord.editor)).where(
                TimeRecord.user_id.in_(user_ids),
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.deleted_at.is_(None),
                TimeRecord.is_ignored.is_(False),
            )
            adj_stmt = select(AdjustmentRequest).where(
                AdjustmentRequest.user_id.in_(user_ids),
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None),
            )
            all_records_batch = list((await session.scalars(rec_stmt)).all())
            all_adjustments_batch = list((await session.scalars(adj_stmt)).all())
            holidays_batch = await async_holiday_repository.get_by_month(session, month, year)
        else:
            if not user_ids:
                return [], [], holiday_repository.get_by_month(session, month, year)
            all_records_batch = session.query(TimeRecord).filter(
                TimeRecord.user_id.in_(user_ids),
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.deleted_at.is_(None),
                TimeRecord.is_ignored == False
            ).all()
            all_adjustments_batch = session.query(AdjustmentRequest).filter(
                AdjustmentRequest.user_id.in_(user_ids),
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None)
            ).all()
            holidays_batch = holiday_repository.get_by_month(session, month, year)
        return all_records_batch, all_adjustments_batch, holidays_batch

    async def _generate_user_reports_list(self, session: Any, users: list[User], month: int, year: int,
                                          current_user: User | None, all_records_batch: list,
                                          all_adjustments_batch: list, holidays_batch: list):
        records_by_user = {}
        for r in all_records_batch:
            records_by_user.setdefault(r.user_id, []).append(r)

        adjustments_by_user = {}
        for a in all_adjustments_batch:
            adjustments_by_user.setdefault(a.user_id, []).append(a)

        user_reports = []
        for user in users:
            report = await report_service.get_advanced_user_report(
                session, user.id, month, year, current_user,
                prefetched_records=records_by_user.get(user.id, []),
                prefetched_adjustments=adjustments_by_user.get(user.id, []),
                prefetched_holidays=holidays_batch
            )
            has_waiver = report and any(day.adjustment_id is not None for day in report.daily_details)
            if report and (report.summary.total_worked_minutes > 0 or has_waiver):
                user_reports.append((user, report))
        return user_reports

    def _resolve_target_period(self, month: int | None, year: int | None) -> tuple[int, int, datetime]:
        now = datetime.now()
        month_val = month if month else now.month
        year_val = year if year else now.year
        return month_val, year_val, now

    async def _validate_export_access(
            self, current_user: User | None, session: Any, month: int, year: int, now: datetime
    ) -> None:
        if not current_user:
            return
        report_service.check_report_permission(current_user)
        if session is not None:
            await report_service.validate_excel_export_permission(
                db=session, current_user=current_user, month=month, year=year, now=now
            )

    async def _resolve_cached_closure_file(self, session: Any, month: int, year: int) -> FileResponse | None:
        closure = await async_payroll_repository.get_by_month(session, month, year)
        if not closure or not getattr(closure, "is_closed", None) or not getattr(closure, "report_path", None):
            return None
        report_path = str(closure.report_path)
        full_path = (
            report_path
            if os.path.isabs(report_path)
            else os.path.join(settings.UPLOAD_DIR, report_path)
        )
        if os.path.exists(full_path) and os.path.isfile(full_path):
            filename = f"folha_ponto_{month:02d}_{year}.xlsx"
            return FileResponse(
                path=full_path,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=filename,
            )
        return None

    async def export_monthly_report(
            self,
            month: int | None = None,
            year: int | None = None,
            employee_ids: list[int] | None = None,
            current_user: User | None = None,
            db: Any | None = None,
    ) -> Response:
        session = db if db is not None else self.db
        month_val, year_val, now = self._resolve_target_period(month, year)
        await self._validate_export_access(current_user, session, month_val, year_val, now)

        if not employee_ids and session is not None:
            cached_file = await self._resolve_cached_closure_file(session, month_val, year_val)
            if cached_file:
                return cached_file

        file_stream = await self.generate_excel_report(
            db=session,
            month=month_val,
            year=year_val,
            employee_ids=employee_ids,
            current_user=current_user,
        )
        filename = f"folha_ponto_{month_val}_{year_val}.xlsx"
        return StreamingResponse(
            file_stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    async def generate_excel_report(self, db: Any | None = None, month: int = 0, year: int = 0,
                                     employee_ids: list[int] | None = None,
                               current_user: User | None = None) -> BytesIO:
        session = db if db is not None else self.db
        assert session is not None
        if current_user:
            self._validate_employee_report_period(current_user, month, year)

        users, company = await self._fetch_users_and_company(session, employee_ids)
        logo_path = self._resolve_logo_path(company)

        user_ids = [u.id for u in users]
        start_date, end_date = report_service.get_month_range(month, year)
        tz = ZoneInfo(settings.TIMEZONE)
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        all_records_batch, all_adjustments_batch, holidays_batch = await self._fetch_batch_data(
            session, user_ids, start_dt, end_dt, start_date, end_date, month, year
        )

        user_reports = await self._generate_user_reports_list(
            session, users, month, year, current_user, all_records_batch, all_adjustments_batch, holidays_batch
        )

        return self.workbook_builder.build(
            month, year, user_reports, company, logo_path, start_date, end_date
        )


excel_service = ExcelService()
