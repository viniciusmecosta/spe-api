import locale
import logging
from calendar import monthrange
from datetime import date, datetime
from fastapi import Depends
from sqlalchemy import exists, extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_service import (
    daily_summary_service,
)
from app.features.holidays.holiday_repository import (
    async_holiday_repository,
    holiday_repository,
)
from app.features.payroll.payroll_models import PayrollClosure
from app.features.reports.report_exceptions import (
    EmployeePreviousMonthOnlyError,
    PayrollNotClosedForReportError,
    PendingAdjustmentsExistError,
    ReportAccessDeniedError,
    ReportExportPermissionError,
    ReportGlobalPermissionError,
    ReportNotFoundOrIncompleteError,
    ReportUserNotFoundError,
)
from app.features.reports.report_response_builder import ReportResponseBuilder
from app.features.reports.report_schemas import (
    AdvancedUserReportResponse,
    HistoryResponse,
    UserPayrollSummary,
)
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_repository import (
    async_time_record_repository,
    time_record_repository,
)
from app.features.timesheets.anomaly_service import anomaly_service
from app.features.users.user_models import User
from app.features.users.user_repository import (
    async_user_repository,
    user_repository,
)
from app.shared import deps
from app.shared.enums import AdjustmentStatus, UserRole

logger = logging.getLogger(__name__)

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except locale.Error:
    pass


class ReportService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db
        self.response_builder = ReportResponseBuilder()

    def get_month_range(self, month: int, year: int) -> tuple[date, date]:
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        return start_date, end_date

    _get_month_range = get_month_range

    async def _calculate_period(
            self, session: Any, user_id: int, start_date: date, end_date: date,
            records: list[TimeRecord], adjustments: list[AdjustmentRequest],
            holidays: list, schedules: list,
    ):
        return await daily_summary_service.build_period(
            session, user_id, start_date, end_date,
            records, adjustments, holidays, schedules,
        )


    def apply_employee_filters(self, query, employee_ids: list[int] | None = None):
        query = query.filter(User.role == UserRole.EMPLOYEE)
        query = query.filter(User.is_exempt_from_rules.is_(False))
        if employee_ids:
            query = query.filter(User.id.in_(employee_ids))
        return query

    _apply_employee_filters = apply_employee_filters


    async def _fetch_history_data(self, session, user_id, start_dt, end_dt, start_date, end_date, month, year, ignore_excessive):
        if hasattr(session, "sync_session"):
            records = await async_time_record_repository.get_by_range(session, user_id, start_dt, end_dt)
            holidays = await async_holiday_repository.get_by_month(session, month, year)
            anomalies = await anomaly_service.get_anomalies(session, start_date, end_date, user_id, ignore_excessive_hours=ignore_excessive, ignore_extra_time=True)
            adj_stmt = select(AdjustmentRequest).where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None)
            )
            adj_res = await session.scalars(adj_stmt)
            all_adjustments = list(adj_res.all())
        else:
            records = time_record_repository.get_by_range(session, user_id, start_dt, end_dt)
            holidays = holiday_repository.get_by_month(session, month, year)
            anomalies = anomaly_service.get_anomalies(session, start_date, end_date, user_id, ignore_excessive_hours=ignore_excessive, ignore_extra_time=True)
            if hasattr(anomalies, "__await__"):
                anomalies = await anomalies
            all_adjustments = session.query(AdjustmentRequest).filter(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None)
            ).all()
        return records, holidays, anomalies, all_adjustments


    async def get_history_report(self, db: Any | None = None, user_id: int = 0, month: int | None = None,
                                 year: int | None = None,
                            current_user: User | None = None) -> HistoryResponse:
        session = db if db is not None else self.db
        assert session is not None
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        today_date = now.date()

        month = month or now.month
        year = year or now.year

        start_date, end_date = self._get_month_range(month, year)

        if year == now.year and month == now.month:
            end_date = min(end_date, now.date())
        elif datetime(year, month, 1).date() > now.date():
            return HistoryResponse(month=month, year=year, total_worked_time="00:00", total_accounted_time="00:00", days=[])

        if hasattr(session, "sync_session"):
            user = await async_user_repository.get(session, user_id)
        else:
            user = user_repository.get(session, user_id)
        if not user:
            raise ReportUserNotFoundError(user_id=user_id)

        if current_user is not None:
            self.check_user_report_access(
                current_user, user_id, detail="Sem permissão para acessar o histórico deste usuário."
            )

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        records, holidays, anomalies, all_adjustments = await self._fetch_history_data(
            session, user_id, start_dt, end_dt, start_date, end_date, month, year, (current_user.id == user_id)
        )

        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]

        period_result = await self._calculate_period(
            session, user_id, start_date, end_date, records,
            all_adjustments, holidays, user.historical_schedules,
        )

        history_days = self.response_builder.build_history_days(
            start_date, end_date, today_date, records, holidays, anomalies, period_result, is_manager, user, all_adjustments
        )

        total_month_minutes = int(round(period_result.total_gross_worked_seconds / 60))
        total_month_hours = total_month_minutes // 60
        month_minutes = total_month_minutes % 60

        total_acc_minutes = int(round(period_result.total_accounted_seconds / 60))
        total_acc_hours = total_acc_minutes // 60
        month_acc_mins = total_acc_minutes % 60

        return HistoryResponse(
            month=month,
            year=year,
            total_worked_time=f"{total_month_hours:02d}:{month_minutes:02d}",
            total_accounted_time=f"{total_acc_hours:02d}:{month_acc_mins:02d}",
            days=history_days
        )

    async def _fetch_report_data(self, db: Any, user_id: int, month: int, year: int,
                           start_dt: datetime, end_dt: datetime,
                           prefetched_records, prefetched_adjustments, prefetched_holidays):
        all_records = prefetched_records
        holidays = prefetched_holidays
        all_adjustments = prefetched_adjustments
        
        is_async = hasattr(db, "sync_session")

        if all_records is None:
            if is_async:
                all_records = await async_time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
            else:
                all_records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
                
        if holidays is None:
            if is_async:
                holidays = await async_holiday_repository.get_by_month(db, month, year)
            else:
                holidays = holiday_repository.get_by_month(db, month, year)
                
        if all_adjustments is None:
            if is_async:
                adj_stmt = select(AdjustmentRequest).where(
                    AdjustmentRequest.user_id == user_id,
                    AdjustmentRequest.target_date >= start_dt.date(),
                    AdjustmentRequest.target_date <= end_dt.date(),
                    AdjustmentRequest.deleted_at.is_(None)
                )
                adj_res = await db.scalars(adj_stmt)
                all_adjustments = list(adj_res.all())
            else:
                all_adjustments = db.query(AdjustmentRequest).filter(
                    AdjustmentRequest.user_id == user_id,
                    AdjustmentRequest.target_date >= start_dt.date(),
                    AdjustmentRequest.target_date <= end_dt.date(),
                    AdjustmentRequest.deleted_at.is_(None)
                ).all()

        return all_records, all_adjustments, holidays


    async def get_advanced_user_report(self, db: Any | None = None, user_id: int = 0, month: int = 0, year: int = 0,
                                 current_user: User | None = None,
                                 prefetched_records: list[TimeRecord] | None = None,
                                 prefetched_adjustments: list | None = None,
                                 prefetched_holidays: list | None = None) -> AdvancedUserReportResponse | None:
        session = db if db is not None else self.db
        assert session is not None
        start_date, end_date = self._get_month_range(month, year)
        if hasattr(session, "sync_session"):
            user = await async_user_repository.get(session, user_id)
        else:
            user = user_repository.get(session, user_id)
        if not user:
            return None

        has_schedule = bool(user.historical_schedules)
        tz = ZoneInfo(settings.TIMEZONE)
        today_date = datetime.now(tz).date()

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        all_records, all_adjustments, holidays = await self._fetch_report_data(
            session, user_id, month, year, start_dt, end_dt,
            prefetched_records, prefetched_adjustments, prefetched_holidays
        )

        is_maintainer = current_user is not None and current_user.role == UserRole.MAINTAINER

        period_result = await self._calculate_period(
            session, user_id, start_date, end_date, all_records,
            all_adjustments, holidays, user.historical_schedules,
        )

        total_worked_seconds = period_result.total_gross_worked_seconds
        total_expected_seconds = period_result.total_expected_seconds
        total_extra_hours = period_result.total_extra_seconds / 3600.0
        total_missing_hours = period_result.total_missing_seconds / 3600.0

        daily_details, days_worked_count, absences_count = self.response_builder.build_advanced_daily_details(
            start_date, end_date, today_date, all_records, holidays, period_result, has_schedule, is_maintainer, user, all_adjustments
        )

        summary = UserPayrollSummary(
            user_id=user.id,
            user_name=user.name,
            total_worked_time=self.response_builder.format_duration(total_worked_seconds),
            total_expected_time=self.response_builder.format_duration(total_expected_seconds),
            total_accounted_time=self.response_builder.format_duration(period_result.total_accounted_seconds),
            total_worked_minutes=int(round(total_worked_seconds / 60)),
            total_expected_minutes=int(round(total_expected_seconds / 60)),
            total_accounted_minutes=int(round(period_result.total_accounted_seconds / 60)),
            days_worked=days_worked_count,
            absences=absences_count,
            total_worked_hours=round(total_worked_seconds / 3600.0, 2),
            total_expected_hours=round(total_expected_seconds / 3600.0, 2),
            total_extra_hours=round(total_extra_hours, 2),
            total_missing_hours=round(total_missing_hours, 2),
            final_balance=round(total_extra_hours - total_missing_hours, 2)
        )

        return AdvancedUserReportResponse(summary=summary, daily_details=daily_details)

    def check_report_permission(self, current_user: User) -> None:
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if not is_manager and not current_user.can_export_report:
            raise ReportGlobalPermissionError()

    def check_user_report_access(self, current_user: User, user_id: int,
                                 detail: str | None = None) -> None:
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if not is_manager and not current_user.can_export_report and current_user.id != user_id:
            raise ReportAccessDeniedError(user_id=user_id, detail=detail)

    async def get_advanced_user_report_or_404(
            self, db: Any | None = None, user_id: int = 0, month: int | None = None, year: int | None = None,
            current_user: User | None = None
    ) -> AdvancedUserReportResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        self.check_user_report_access(
            current_user, user_id, detail="Sem permissão para ver relatório de outros usuários."
        )
        now = datetime.now()
        month_val = month if month else now.month
        year_val = year if year else now.year
        report = await self.get_advanced_user_report(session, user_id, month_val, year_val, current_user)
        if not report:
            raise ReportNotFoundOrIncompleteError(user_id=user_id)
        return report

    async def _validate_manager_export_permission(self, session, month: int, year: int) -> None:
        if hasattr(session, "sync_session"):
            stmt = select(exists().where(
                AdjustmentRequest.status == AdjustmentStatus.PENDING,
                extract("month", AdjustmentRequest.target_date) == month,
                extract("year", AdjustmentRequest.target_date) == year,
            ))
            pending_adjustments = await session.scalar(stmt)
        else:
            pending_adjustments = session.query(exists().where(
                AdjustmentRequest.status == AdjustmentStatus.PENDING,
                extract("month", AdjustmentRequest.target_date) == month,
                extract("year", AdjustmentRequest.target_date) == year,
            )).scalar()

        if pending_adjustments:
            raise PendingAdjustmentsExistError()

    async def _validate_employee_export_permission(self, session, current_user: User, month: int, year: int, now: datetime) -> None:
        if not current_user.can_export_report:
            raise ReportExportPermissionError()

        prev_month = now.month - 1 if now.month > 1 else 12
        prev_year = now.year if now.month > 1 else now.year - 1

        if month != prev_month or year != prev_year:
            raise EmployeePreviousMonthOnlyError()

        if hasattr(session, "sync_session"):
            stmt = select(exists().where(
                PayrollClosure.month == month,
                PayrollClosure.year == year,
                PayrollClosure.is_closed == True,
                PayrollClosure.deleted_at.is_(None),
            ))
            payroll_closed = await session.scalar(stmt)
        else:
            payroll_closed = session.query(exists().where(
                PayrollClosure.month == month,
                PayrollClosure.year == year,
                PayrollClosure.is_closed == True,
                PayrollClosure.deleted_at.is_(None),
            )).scalar()

        if not payroll_closed:
            raise PayrollNotClosedForReportError()

    async def validate_excel_export_permission(
            self, db: Any | None = None, current_user: User | None = None, month: int = 0, year: int = 0,
            now: datetime | None = None
    ) -> None:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        assert now is not None
        if current_user.role == UserRole.MAINTAINER:
            return
        if current_user.role == UserRole.MANAGER:
            await self._validate_manager_export_permission(session, month, year)
            return
        await self._validate_employee_export_permission(session, current_user, month, year, now)


report_service = ReportService()
