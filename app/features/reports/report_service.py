import locale
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import exists, extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
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
from app.features.reports.report_schemas import (
    AdvancedUserReportResponse,
    DailyReportItem,
    HistoryDay,
    HistoryPunch,
    HistoryResponse,
    PunchDetail,
    ReportAdjustmentItem,
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
from app.shared import time_calculation_service as time_calc_mod
from app.shared.enums import AdjustmentStatus, AdjustmentType, DayOfWeek, UserRole

logger = logging.getLogger(__name__)

WEEKEND_STATUS = "Fim de semana"

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except locale.Error:
    pass


class ReportService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db

    def get_month_range(self, month: int, year: int) -> tuple[date, date]:
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        return start_date, end_date

    _get_month_range = get_month_range

    def _format_duration(self, total_seconds: float) -> str:
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"

    def apply_employee_filters(self, query, employee_ids: list[int] | None = None):
        query = query.filter(User.role == UserRole.EMPLOYEE)
        query = query.filter(User.is_exempt_from_rules.is_(False))
        if employee_ids:
            query = query.filter(User.id.in_(employee_ids))
        return query

    _apply_employee_filters = apply_employee_filters

    def _build_history_punches(self, day_records, is_manager) -> list:
        punches = []
        for rec in day_records:
            punch_data = {
                "id": rec.id,
                "short_id": rec.short_id,
                "time": rec.record_datetime.strftime("%H:%M"),
                "record_type": rec.record_type.value,
            }
            if is_manager:
                punch_data.update({
                    "ip_address": rec.ip_address,
                    "device_name": rec.device_name,
                    "platform": rec.platform,
                    "biometric_id": rec.biometric_id,
                    "edited_by": rec.editor_name,
                    "edit_justification": rec.edit_justification if rec.edit_justification else None
                })
            punches.append(HistoryPunch(**punch_data))
        return punches

    def _determine_history_status(self, has_records: bool, has_holiday: bool, is_weekend: bool, has_abono: bool,
                                  is_today: bool) -> str:
        if has_records:
            return "Normal"
        if has_holiday:
            return "Feriado"
        if is_weekend:
            return WEEKEND_STATUS
        if has_abono:
            return "Abono"
        if is_today:
            return ""
        return "Falta"

    def _determine_excess_info(self, accounted_res, daily_excess_adj, schedule: Any | None = None,
                               is_manager: bool = True) -> tuple[bool, str | None, int | None]:
        is_enabled = bool(schedule and getattr(schedule, "is_daily_excess_enabled", False))
        if not is_enabled:
            return False, None, None

        has_excess = bool(accounted_res.total_excess_seconds > 0 or (daily_excess_adj is not None))
        daily_excess_id = daily_excess_adj.id if daily_excess_adj else None
        if daily_excess_adj:
            excess_status = daily_excess_adj.status.value
        elif accounted_res.total_excess_seconds > 0:
            excess_status = AdjustmentStatus.PENDING.value
        else:
            excess_status = None

        if not is_manager and excess_status == AdjustmentStatus.PENDING.value:
            return False, None, None

        return has_excess, excess_status, daily_excess_id

    def _to_report_adjustment_item(self, adj: Any, current: date) -> ReportAdjustmentItem:
        if isinstance(adj, ReportAdjustmentItem):
            return adj
        if isinstance(adj, dict):
            return ReportAdjustmentItem(**adj)
        c_at = getattr(adj, 'created_at', None)
        r_at = getattr(adj, 'reviewed_at', None)
        return ReportAdjustmentItem(
            id=getattr(adj, 'id', 0),
            user_id=getattr(adj, 'user_id', 0),
            adjustment_type=getattr(adj, 'adjustment_type', AdjustmentType.OTHER),
            record_type=getattr(adj, 'record_type', None),
            target_date=getattr(adj, 'target_date', current),
            time=getattr(adj, 'time', None),
            amount_hours=getattr(adj, 'amount_hours', None),
            approved_amount_hours=getattr(adj, 'approved_amount_hours', None),
            reason_text=getattr(adj, 'reason_text', None),
            status=getattr(adj, 'status', AdjustmentStatus.PENDING),
            manager_id=getattr(adj, 'manager_id', None),
            manager_comment=getattr(adj, 'manager_comment', None),
            created_at=c_at if isinstance(c_at, datetime) else None,
            reviewed_at=r_at if isinstance(r_at, datetime) else None,
        )

    def _build_day_adjustments_list(self, day_adjustments: list | None, current: date, is_manager: bool = True) -> list[
        ReportAdjustmentItem]:
        filtered = []
        for adj in (day_adjustments or []):
            item = self._to_report_adjustment_item(adj, current)
            if not is_manager and item.adjustment_type == AdjustmentType.DAILY_EXCESS and item.status == AdjustmentStatus.PENDING:
                continue
            filtered.append(item)
        return filtered

    def _build_history_day(
            self,
            current: date,
            today_date: date,
            records: list[TimeRecord],
            holidays: list,
            anomalies: list,
            period_result,
            is_manager: bool,
            schedule: Any | None = None,
            daily_excess_adj: AdjustmentRequest | None = None,
            day_adjustments: list[AdjustmentRequest] | None = None,
    ) -> HistoryDay:
        day_records = [r for r in records if r.record_datetime.date() == current]
        day_records.sort(key=lambda x: x.record_datetime)

        holiday = next((h for h in holidays if h.date == current), None)
        day_anomalies = [a for a in anomalies if a.date == current]

        daily_res = period_result.daily_results[current]
        worked_seconds = daily_res.net_worked_seconds
        abono = period_result.daily_waivers[current]

        accounted_res = time_calc_mod.time_calculation_service.calculate_accounted_time(
            day_records=day_records,
            schedule=schedule,
            daily_excess_adj=daily_excess_adj,
        )
        accounted_time_str = self._format_duration(accounted_res.accounted_seconds)
        has_excess, excess_status, daily_excess_id = self._determine_excess_info(accounted_res, daily_excess_adj,
                                                                                 schedule, is_manager)

        day_adjustments_list = self._build_day_adjustments_list(day_adjustments, current, is_manager)
        punches = self._build_history_punches(day_records, is_manager)

        target_day = DayOfWeek(current.weekday())
        day_name = target_day.abreviado
        is_weekend = target_day in (DayOfWeek.SABADO, DayOfWeek.DOMINGO)

        status = self._determine_history_status(
            has_records=bool(day_records),
            has_holiday=bool(holiday),
            is_weekend=is_weekend,
            has_abono=bool(abono),
            is_today=current == today_date
        )

        total_minutes = int(round(worked_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        worked_time_str = f"{hours:02d}:{minutes:02d}"

        anomalies_list = [a.description for a in day_anomalies]

        return HistoryDay(
            date=current,
            day_name=day_name,
            is_holiday=bool(holiday),
            is_weekend=is_weekend,
            is_absent=(status == "Falta"),
            status=status,
            holiday_name=holiday.name if holiday else None,
            worked_time=worked_time_str,
            accounted_time=accounted_time_str,
            punches=punches,
            has_anomaly=len(anomalies_list) > 0,
            anomalies=anomalies_list,
            abono_hours=abono.amount_hours if abono else None,
            abono_id=abono.id if abono and is_manager else None,
            has_excess=has_excess,
            excess_status=excess_status,
            daily_excess_id=daily_excess_id,
            adjustments=day_adjustments_list,
        )

    def _build_detailed_punches(self, day_records: list[TimeRecord], is_maintainer: bool) -> list[PunchDetail]:
        if not is_maintainer:
            return []
        detailed_punches = []
        for rec in day_records:
            detailed_punches.append(PunchDetail(
                id=rec.id,
                short_id=rec.short_id,
                time=rec.record_datetime.strftime("%H:%M:%S"),
                record_type=rec.record_type.value,
                ip_address=rec.ip_address,
                device_name=rec.device_name,
                platform=rec.platform,
                biometric_id=rec.biometric_id,
                edited_by=rec.editor_name,
                edit_justification=rec.edit_justification if rec.edit_justification else None
            ))
        return detailed_punches

    def _determine_daily_status(self, is_future: bool, is_holiday: bool, is_weekend: bool, is_waiver: bool,
                                worked_seconds: float, expected_seconds: float, is_today: bool,
                                has_schedule: bool) -> str:
        if is_holiday:
            return "Feriado"
        if is_waiver:
            return "Abono"
            
        if is_future:
            if is_weekend:
                return WEEKEND_STATUS
            return ""
            
        if is_weekend:
            if worked_seconds > 0:
                return "Normal"
            return WEEKEND_STATUS
            
        if worked_seconds > 0:
            return "Normal"
            
        if expected_seconds > 0:
            if is_today:
                return ""
            return "Falta"
            
        if not has_schedule:
            return "-"
            
        return "Normal"

    def _compute_daily_hours_and_balance(self, daily_res, expected_seconds: float):
        worked_seconds = daily_res.net_worked_seconds
        day_worked_hours = worked_seconds / 3600.0
        day_expected_hours = expected_seconds / 3600.0
        day_extra = daily_res.extra_seconds / 3600.0
        day_missing = daily_res.missing_seconds / 3600.0
        day_balance = day_extra - day_missing
        return worked_seconds, day_worked_hours, day_expected_hours, day_extra, day_missing, day_balance

    def _build_daily_report_item(
            self,
            current: date,
            today_date: date,
            all_records: list[TimeRecord],
            holidays: list,
            period_result,
            has_schedule: bool,
            is_maintainer: bool,
            schedule: Any | None = None,
            daily_excess_adj: AdjustmentRequest | None = None,
            day_adjustments: list[AdjustmentRequest] | None = None,
    ) -> DailyReportItem:
        is_future = current > today_date
        is_today = current == today_date

        day_records = sorted([r for r in all_records if r.record_datetime.date() == current], key=lambda x: x.record_datetime)
        holiday = next((h for h in holidays if h.date == current), None)
        holiday_name = holiday.name if holiday else None

        daily_res = period_result.daily_results[current]
        adjustment_day = period_result.daily_waivers[current]
        is_waiver = adjustment_day is not None
        adj_id = adjustment_day.id if adjustment_day else None
        target_day = DayOfWeek(current.weekday())
        is_weekend = target_day in (DayOfWeek.SABADO, DayOfWeek.DOMINGO)

        expected_seconds = period_result.daily_expected_seconds[current]
        worked_seconds, day_worked_hours, day_expected_hours, day_extra, day_missing, day_balance = self._compute_daily_hours_and_balance(daily_res, expected_seconds)

        accounted_res = time_calc_mod.time_calculation_service.calculate_accounted_time(
            day_records=day_records, schedule=schedule, daily_excess_adj=daily_excess_adj
        )
        has_excess, excess_status, daily_excess_id = self._determine_excess_info(accounted_res, daily_excess_adj,
                                                                                 schedule, is_maintainer)

        punches = list(daily_res.punches)
        if is_waiver:
            formatted_waiver = self._format_duration(daily_res.waiver_seconds)
            if formatted_waiver and formatted_waiver != "00:00":
                punches.append(f"Abono: {formatted_waiver}")

        status = self._determine_daily_status(
            is_future, holiday is not None, is_weekend, is_waiver, worked_seconds, expected_seconds, is_today, has_schedule
        )

        return DailyReportItem(
            date=current,
            day_name=target_day.abreviado,
            is_holiday=holiday is not None,
            holiday_name=holiday_name,
            is_weekend=is_weekend,
            status=status,
            entries=daily_res.entries,
            exits=daily_res.exits,
            punches=punches,
            detailed_punches=self._build_detailed_punches(day_records, is_maintainer) if is_maintainer else None,
            adjustment_id=adj_id,
            worked_hours=round(day_worked_hours, 2),
            expected_hours=round(day_expected_hours, 2),
            balance_hours=round(day_balance, 2),
            extra_hours=round(day_extra, 2),
            missing_hours=round(day_missing, 2),
            worked_minutes=int(round(worked_seconds / 60)),
            worked_time=self._format_duration(worked_seconds),
            accounted_time=self._format_duration(accounted_res.accounted_seconds),
            expected_time=self._format_duration(expected_seconds),
            unapproved_extra_time=self._format_duration(daily_res.unapproved_extra_seconds),
            has_excess=has_excess,
            excess_status=excess_status,
            daily_excess_id=daily_excess_id,
            adjustments=self._build_day_adjustments_list(day_adjustments, current),
        )

    async def _fetch_history_data(self, session, user_id, start_dt, end_dt, start_date, end_date, month, year, ignore_excessive):
        if hasattr(session, "sync_session"):
            records = await async_time_record_repository.get_by_range(session, user_id, start_dt, end_dt)
            holidays = await async_holiday_repository.get_by_month(session, month, year)
            anomalies = await anomaly_service.get_anomalies(session, start_date, end_date, user_id, ignore_excessive_hours=ignore_excessive)
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
            anomalies = anomaly_service.get_anomalies(session, start_date, end_date, user_id, ignore_excessive_hours=ignore_excessive)
            if hasattr(anomalies, "__await__"):
                anomalies = await anomalies
            all_adjustments = session.query(AdjustmentRequest).filter(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None)
            ).all()
        return records, holidays, anomalies, all_adjustments

    def _get_schedule_for_date(self, user, current_date, target_day_val):
        if not user or not user.historical_schedules:
            return None
        for s in user.historical_schedules:
            if s.valid_from <= current_date:
                if s.valid_until is None or s.valid_until >= current_date:
                    if s.day_of_week == target_day_val:
                        return s
        return None

    def _build_history_days_loop(self, start_date, end_date, today_date, records, holidays, anomalies, period_result, is_manager, user, all_adjustments):
        history_days = []
        adjs_by_date = {}
        excess_by_date = {}
        for adj in all_adjustments:
            adjs_by_date.setdefault(adj.target_date, []).append(adj)
            if adj.adjustment_type == AdjustmentType.DAILY_EXCESS:
                excess_by_date[adj.target_date] = adj
                
        current = start_date
        while current <= end_date:
            target_day_val = DayOfWeek.from_date(current).value
            day_schedule = self._get_schedule_for_date(user, current, target_day_val)
            day_excess = excess_by_date.get(current)
            day_adjs = adjs_by_date.get(current, [])

            history_day = self._build_history_day(
                current=current,
                today_date=today_date,
                records=records,
                holidays=holidays,
                anomalies=anomalies,
                period_result=period_result,
                is_manager=is_manager,
                schedule=day_schedule,
                daily_excess_adj=day_excess,
                day_adjustments=day_adjs,
            )
            history_days.append(history_day)
            current += timedelta(days=1)
        return history_days

    async def get_history_report(self, db: Any | None = None, user_id: int = 0, month: int | None = None,
                                 year: int | None = None,
                            current_user: User | None = None) -> HistoryResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
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

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        records, holidays, anomalies, all_adjustments = await self._fetch_history_data(
            session, user_id, start_dt, end_dt, start_date, end_date, month, year, (current_user.id == user_id)
        )

        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]

        period_result = time_calc_mod.time_calculation_service.calculate_period_time(
            start_date=start_date,
            end_date=end_date,
            records=records,
            adjustments=all_adjustments,
            holidays=holidays,
            historical_schedules=user.historical_schedules if user else []
        )

        history_days = self._build_history_days_loop(
            start_date, end_date, today_date, records, holidays, anomalies, period_result, is_manager, user, all_adjustments
        )

        total_month_minutes = int(round(period_result.total_net_worked_seconds / 60))
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

    def _build_advanced_daily_details(self, start_date, end_date, today_date, all_records, holidays, period_result, has_schedule, is_maintainer, user, all_adjustments):
        daily_details = []
        days_worked_count = 0
        absences_count = 0
        
        adjs_by_date = {}
        excess_by_date = {}
        for adj in all_adjustments:
            adjs_by_date.setdefault(adj.target_date, []).append(adj)
            if adj.adjustment_type == AdjustmentType.DAILY_EXCESS:
                excess_by_date[adj.target_date] = adj
                
        current = start_date
        while current <= end_date:
            target_day_val = DayOfWeek.from_date(current).value
            day_schedule = self._get_schedule_for_date(user, current, target_day_val)
            day_excess = excess_by_date.get(current)
            day_adjs = adjs_by_date.get(current, [])

            item = self._build_daily_report_item(
                current=current,
                today_date=today_date,
                all_records=all_records,
                holidays=holidays,
                period_result=period_result,
                has_schedule=has_schedule,
                is_maintainer=is_maintainer,
                schedule=day_schedule,
                daily_excess_adj=day_excess,
                day_adjustments=day_adjs,
            )
            daily_details.append(item)

            if item.worked_hours > 0:
                days_worked_count += 1
            if item.worked_hours == 0 and item.expected_hours > 0 and not item.is_weekend and not item.is_holiday and not item.adjustment_id and current < today_date:
                absences_count += 1

            current += timedelta(days=1)
        return daily_details, days_worked_count, absences_count

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

        period_result = time_calc_mod.time_calculation_service.calculate_period_time(
            start_date=start_date,
            end_date=end_date,
            records=all_records,
            adjustments=all_adjustments,
            holidays=holidays,
            historical_schedules=user.historical_schedules if user else []
        )

        total_worked_seconds = period_result.total_net_worked_seconds
        total_expected_seconds = period_result.total_expected_seconds
        total_extra_hours = period_result.total_extra_seconds / 3600.0
        total_missing_hours = period_result.total_missing_seconds / 3600.0

        daily_details, days_worked_count, absences_count = self._build_advanced_daily_details(
            start_date, end_date, today_date, all_records, holidays, period_result, has_schedule, is_maintainer, user, all_adjustments
        )

        summary = UserPayrollSummary(
            user_id=user.id,
            user_name=user.name,
            total_worked_time=self._format_duration(total_worked_seconds),
            total_expected_time=self._format_duration(total_expected_seconds),
            total_accounted_time=self._format_duration(period_result.total_accounted_seconds),
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
            self, db: Any | None = None, user_id: int = 0, month: int = 0, year: int = 0,
            current_user: User | None = None
    ) -> AdvancedUserReportResponse:
        session = db if db is not None else self.db
        assert session is not None
        assert current_user is not None
        report = await self.get_advanced_user_report(session, user_id, month, year, current_user)
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
