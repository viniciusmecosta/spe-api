import locale
import logging
from calendar import monthrange
from datetime import date, timedelta, datetime
from sqlalchemy import extract
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.domain.models.enums import UserRole
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User
from app.repositories.holiday_repository import holiday_repository
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.report import (
    MonthlyReportResponse, UserPayrollSummary, AdvancedUserReportResponse,
    DailyReportItem, PunchDetail,
    HistoryResponse, HistoryDay, HistoryPunch
)
from app.services.anomaly_service import anomaly_service
from app.utils.formatters import get_weekday_name

logger = logging.getLogger(__name__)

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except locale.Error:
    pass


class ReportService:
    def _get_month_range(self, month: int, year: int):
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        return start_date, end_date

    def _format_duration(self, total_seconds: float) -> str:
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"

    def _apply_employee_filters(self, query, employee_ids: Optional[List[int]] = None):
        query = query.filter(User.role == UserRole.EMPLOYEE)
        query = query.filter(User.is_exempt_from_rules.is_(False))
        if employee_ids:
            query = query.filter(User.id.in_(employee_ids))
        return query

    def _build_history_day(
            self,
            current: date,
            today_date: date,
            records: List[TimeRecord],
            holidays: List,
            anomalies: List,
            period_result,
            is_manager: bool
    ) -> HistoryDay:
        day_records = [r for r in records if r.record_datetime.date() == current]
        day_records.sort(key=lambda x: x.record_datetime)

        holiday = next((h for h in holidays if h.date == current), None)

        if current < today_date:
            day_anomalies = [a for a in anomalies if a.date == current]
        else:
            day_anomalies = []

        daily_res = period_result.daily_results[current]
        worked_seconds = daily_res.net_worked_seconds
        abono = period_result.daily_waivers[current]

        punches = []
        for rec in day_records:
            punch_data = {
                "id": rec.id,
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

        day_name = get_weekday_name(current.weekday())
        is_weekend = current.weekday() >= 5

        if day_records:
            status = "Normal"
        elif holiday:
            status = "Feriado"
        elif is_weekend:
            status = "Final de semana"
        elif abono:
            status = "Abonado"
        elif current == today_date:
            status = ""
        else:
            status = "Falta"

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
            punches=punches,
            has_anomaly=len(anomalies_list) > 0,
            anomalies=anomalies_list,
            abono_hours=abono.amount_hours if abono else None,
            abono_id=abono.id if abono and is_manager else None
        )

    def _build_daily_report_item(
            def _build_detailed_punches(self, day_records: List[TimeRecord], is_maintainer: bool) -> List[PunchDetail]:
        if not is_maintainer:
            return []
        detailed_punches = []
        for rec in day_records:
            detailed_punches.append(PunchDetail(
                id=rec.id,
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
        if is_future:
            if is_holiday:
                return "Feriado"
            elif is_weekend:
                return "Fim de Semana"
            return ""
        if is_waiver:
            return "Abonado/Atestado"
        if is_holiday:
            return "Feriado"
        if is_weekend:
            if worked_seconds > 0:
                return "Normal"
            return "Fim de Semana"
        if worked_seconds == 0 and expected_seconds > 0:
            if is_today:
                return ""
            return "Falta"
        if not has_schedule and worked_seconds == 0:
            return "-"
        return "Normal"

    def _build_daily_report_item(
            self,
            current: date,
            today_date: date,
            all_records: List[TimeRecord],
            holidays: List,
            period_result,
            has_schedule: bool,
            is_maintainer: bool
    ) -> DailyReportItem:
        is_future = current > today_date
        is_today = current == today_date

        day_records = [r for r in all_records if r.record_datetime.date() == current]
        day_records.sort(key=lambda x: x.record_datetime)

        holiday = next((h for h in holidays if h.date == current), None)
        is_holiday = holiday is not None
        holiday_name = holiday.name if holiday else None

        daily_res = period_result.daily_results[current]
        adjustment_day = period_result.daily_waivers[current]

        is_waiver = adjustment_day is not None
        adj_id = adjustment_day.id if adjustment_day else None
        waiver_credit = daily_res.waiver_seconds

        weekday = current.weekday()
        is_weekend = weekday >= 5

        expected_seconds = period_result.daily_expected_seconds[current]

        worked_seconds = daily_res.net_worked_seconds
        unapproved_extra_seconds = daily_res.unapproved_extra_seconds
        entries = daily_res.entries
        exits = daily_res.exits
        punches = daily_res.punches

        detailed_punches = self._build_detailed_punches(day_records, is_maintainer)

        day_worked_hours = worked_seconds / 3600.0
        day_expected_hours = expected_seconds / 3600.0

        day_balance = 0.0
        if has_schedule:
            day_balance = day_worked_hours - day_expected_hours

        day_extra = day_balance if day_balance > 0 else 0.0
        day_missing = abs(day_balance) if day_balance < 0 else 0.0

        status = self._determine_daily_status(
            is_future, is_holiday, is_weekend, is_waiver, worked_seconds, expected_seconds, is_today, has_schedule
        )
        if is_waiver:
            formatted_waiver = self._format_duration(waiver_credit)
            if formatted_waiver and formatted_waiver != "00:00":
                punches.append(f"Abono: {formatted_waiver}")

        worked_minutes_int = int(round(worked_seconds / 60))

        return DailyReportItem(
            date=current,
            day_name=get_weekday_name(current.weekday()),
            is_holiday=is_holiday,
            holiday_name=holiday_name,
            is_weekend=is_weekend,
            status=status,
            entries=entries,
            exits=exits,
            punches=punches,
            detailed_punches=detailed_punches if is_maintainer else None,
            adjustment_id=adj_id,
            worked_hours=round(day_worked_hours, 2),
            expected_hours=round(day_expected_hours, 2),
            balance_hours=round(day_balance, 2),
            extra_hours=round(day_extra, 2),
            missing_hours=round(day_missing, 2),
            worked_minutes=worked_minutes_int,
            worked_time=self._format_duration(worked_seconds),
            expected_time=self._format_duration(expected_seconds),
            unapproved_extra_time=self._format_duration(unapproved_extra_seconds)
        )

    def get_history_report(self, db: Session, user_id: int, month: Optional[int], year: Optional[int],
                           current_user: User) -> HistoryResponse:
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        today_date = now.date()

        if not month:
            month = now.month
        if not year:
            year = now.year

        start_date, end_date = self._get_month_range(month, year)

        if year == now.year and month == now.month:
            if end_date > now.date():
                end_date = now.date()
        elif datetime(year, month, 1).date() > now.date():
            return HistoryResponse(month=month, year=year, total_worked_time="00:00", days=[])

        user = user_repository.get(db, user_id)
        if not user:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(db, month, year)

        ignore_excessive = (current_user.id == user_id)
        anomalies = anomaly_service.get_anomalies(db, start_date, end_date, user_id,
                                                  ignore_excessive_hours=ignore_excessive)

        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]

        from app.domain.models.adjustment_request import AdjustmentRequest
        all_adjustments = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.deleted_at.is_(None)
        ).all()

        history_days = []

        from app.services.time_calculation_service import time_calculation_service
        period_result = time_calculation_service.calculate_period_time(
            start_date=start_date,
            end_date=end_date,
            records=records,
            adjustments=all_adjustments,
            holidays=holidays,
            historical_schedules=user.historical_schedules if user else []
        )

        current = start_date
        while current <= end_date:
            history_day = self._build_history_day(
                current=current,
                today_date=today_date,
                records=records,
                holidays=holidays,
                anomalies=anomalies,
                period_result=period_result,
                is_manager=is_manager
            )
            history_days.append(history_day)
            current += timedelta(days=1)

        total_month_minutes = int(round(period_result.total_net_worked_seconds / 60))
        total_month_hours = total_month_minutes // 60
        month_minutes = total_month_minutes % 60

        return HistoryResponse(
            month=month,
            year=year,
            total_worked_time=f"{total_month_hours:02d}:{month_minutes:02d}",
            days=history_days
        )

    def get_advanced_user_report(self, db: Session, user_id: int, month: int, year: int,
                                 current_user: Optional[User] = None) -> Optional[AdvancedUserReportResponse]:
        start_date, end_date = self._get_month_range(month, year)
        user = user_repository.get(db, user_id)
        if not user:
            return None

        has_schedule = bool(user.historical_schedules)
        tz = ZoneInfo(settings.TIMEZONE)
        today_date = datetime.now(tz).date()

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        all_records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(db, month, year)

        from app.domain.models.adjustment_request import AdjustmentRequest
        all_adjustments = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.deleted_at.is_(None)
        ).all()

        daily_details = []
        days_worked_count = 0
        absences_count = 0

        is_maintainer = current_user is not None and current_user.role == UserRole.MAINTAINER

        from app.services.time_calculation_service import time_calculation_service
        period_result = time_calculation_service.calculate_period_time(
            start_date=start_date,
            end_date=end_date,
            records=all_records,
            adjustments=all_adjustments,
            holidays=holidays,
            historical_schedules=user.historical_schedules if user else []
        )

        total_worked_seconds = period_result.total_net_worked_seconds
        total_expected_seconds = period_result.total_expected_seconds
        total_extra_hours = 0.0
        total_missing_hours = 0.0

        current = start_date
        while current <= end_date:
            item = self._build_daily_report_item(
                current=current,
                today_date=today_date,
                all_records=all_records,
                holidays=holidays,
                period_result=period_result,
                has_schedule=has_schedule,
                is_maintainer=is_maintainer
            )
            daily_details.append(item)

            if item.worked_hours > 0:
                days_worked_count += 1
            if item.worked_hours == 0 and item.expected_hours > 0 and not item.is_weekend and not item.is_holiday and not item.adjustment_id and current < today_date:
                absences_count += 1

            total_extra_hours += item.extra_hours
            total_missing_hours += item.missing_hours

            current += timedelta(days=1)

        summary = UserPayrollSummary(
            user_id=user.id,
            user_name=user.name,
            total_worked_time=self._format_duration(total_worked_seconds),
            total_expected_time=self._format_duration(total_expected_seconds),
            total_worked_minutes=int(round(total_worked_seconds / 60)),
            total_expected_minutes=int(round(total_expected_seconds / 60)),
            days_worked=days_worked_count,
            absences=absences_count,
            total_worked_hours=round(total_worked_seconds / 3600.0, 2),
            total_expected_hours=round(total_expected_seconds / 3600.0, 2),
            total_extra_hours=round(total_extra_hours, 2),
            total_missing_hours=round(total_missing_hours, 2),
            final_balance=round(total_extra_hours - total_missing_hours, 2)
        )

        return AdvancedUserReportResponse(summary=summary, daily_details=daily_details)

    def get_monthly_summary(self, db: Session, month: int, year: int,
                            employee_ids: Optional[List[int]] = None,
                            current_user: Optional[User] = None) -> MonthlyReportResponse:
        query = db.query(User).options(joinedload(User.historical_schedules))
        query = self._apply_employee_filters(query, employee_ids)
        users = query.all()

        payroll_data = []
        for user in users:
            report = self.get_advanced_user_report(db, user.id, month, year, current_user)
            if report and report.summary.total_worked_minutes > 0:
                payroll_data.append(report.summary)

        return MonthlyReportResponse(month=month, year=year, payroll_data=payroll_data)


report_service = ReportService()
