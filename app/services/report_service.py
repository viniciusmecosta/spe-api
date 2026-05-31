import locale
from calendar import monthrange
from datetime import date, timedelta, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.enums import RecordType, UserRole, AdjustmentType
from app.domain.models.user import User
from app.repositories.adjustment_repository import adjustment_repository
from app.repositories.holiday_repository import holiday_repository
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.report import (
    MonthlyReportResponse, UserPayrollSummary, AdvancedUserReportResponse,
    DailyReportItem, DashboardMetricsResponse, PunchDetail,
    HistoryResponse, HistoryDay, HistoryPunch, MyDashboardResponse, TodayPunch, AnomalyItem,
    TeamHoursResponse, EmployeeHours
)
from app.services.anomaly_service import anomaly_service

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except Exception:
    pass


class ReportService:
    def _get_month_range(self, month: int, year: int):
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        return start_date, end_date

    def _get_day_name(self, dt: date) -> str:
        days = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
        return days[dt.isoweekday() % 7]

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

    def get_dashboard_metrics(self, db: Session) -> DashboardMetricsResponse:
        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()

        active_users = db.query(User).filter(
            User.is_active.is_(True),
            User.role == UserRole.EMPLOYEE,
            User.is_exempt_from_rules.is_(False)
        ).count()

        pending = adjustment_repository.count_pending(db)

        today_start = datetime.combine(today, datetime.min.time(), tzinfo=tz)
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=tz)
        present = time_record_repository.count_unique_users_in_range(db, today_start, today_end)

        return DashboardMetricsResponse(
            total_active_employees=active_users,
            pending_adjustments=pending,
            employees_present_today=present,
            date=today
        )

    def get_my_dashboard(self, db: Session, current_user: User) -> MyDashboardResponse:
        tz = ZoneInfo(settings.TIMEZONE)
        now = datetime.now(tz)
        today_date = now.date()
        start_of_month = date(now.year, now.month, 1)

        start_dt_today = datetime.combine(today_date, datetime.min.time(), tzinfo=tz)
        end_dt_today = datetime.combine(today_date, datetime.max.time(), tzinfo=tz)

        today_records = time_record_repository.get_by_range(db, current_user.id, start_dt_today, end_dt_today)
        today_records.sort(key=lambda x: x.record_datetime)

        today_punches = []
        for rec in today_records:
            today_punches.append(TodayPunch(
                id=rec.id,
                time=rec.record_datetime.strftime("%H:%M"),
                record_type=rec.record_type.value
            ))

        next_punch_type = "ENTRY"
        if today_records:
            last_record = today_records[-1]
            if last_record.record_type == RecordType.ENTRY:
                next_punch_type = "EXIT"

        month_anomalies = []
        if today_date > start_of_month:
            anomalies = anomaly_service.get_anomalies(
                db, start_of_month, today_date - timedelta(days=1), current_user.id, ignore_excessive_hours=True
            )
            for a in anomalies:
                month_anomalies.append(AnomalyItem(
                    date=a.date.strftime("%d/%m/%Y"),
                    description=a.description
                ))

        return MyDashboardResponse(
            full_name=current_user.name,
            next_punch_type=next_punch_type,
            today_punches=today_punches,
            month_anomalies=month_anomalies
        )

    def get_team_worked_hours(self, db: Session, month: int, year: int, current_user: User) -> TeamHoursResponse:
        query = db.query(User).filter(
            User.role == UserRole.EMPLOYEE,
            User.is_exempt_from_rules.is_(False)
        )
        users = query.all()

        employees_data = []
        team_total_minutes = 0

        for user in users:
            report = self.get_advanced_user_report(db, user.id, month, year, current_user)
            if report:
                user_minutes = report.summary.total_worked_minutes
                if user_minutes >= 60:
                    user_hours_rounded = user_minutes // 60
                    employees_data.append(EmployeeHours(
                        user_id=user.id,
                        short_name=user.name,
                        total_hours=float(user_hours_rounded),
                        formatted_time=f"{user_hours_rounded}h"
                    ))
                    team_total_minutes += user_minutes

        t_hours = team_total_minutes // 60

        return TeamHoursResponse(
            month=month,
            year=year,
            team_total_hours=float(t_hours),
            team_formatted_time=f"{t_hours}h",
            employees=employees_data
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
            raise HTTPException(status_code=404, detail="User not found")

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(db, month, year)
        adjustments = adjustment_repository.get_approved_by_range(db, user_id, start_date, end_date)

        ignore_excessive = (current_user.id == user_id)
        anomalies = anomaly_service.get_anomalies(db, start_date, end_date, user_id,
                                                  ignore_excessive_hours=ignore_excessive)

        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]

        total_worked_seconds = 0.0
        history_days = []

        current = start_date
        while current <= end_date:
            day_records = [r for r in records if r.record_datetime.date() == current]
            day_records.sort(key=lambda x: x.record_datetime)

            holiday = next((h for h in holidays if h.date == current), None)

            if current < today_date:
                day_anomalies = [a for a in anomalies if a.date == current]
            else:
                day_anomalies = []

            abono = next((adj for adj in adjustments if
                          adj.target_date == current and adj.adjustment_type == AdjustmentType.WAIVER), None)

            worked_seconds = 0.0
            entry_time = None
            punches = []

            for rec in day_records:
                if rec.record_type == RecordType.ENTRY:
                    entry_time = rec.record_datetime
                elif rec.record_type == RecordType.EXIT and entry_time:
                    worked_seconds += (rec.record_datetime - entry_time).total_seconds()
                    entry_time = None

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
                        "edited_by": rec.edited_by,
                        "edit_justification": rec.edit_justification.value if rec.edit_justification else None,
                        "edit_reason": rec.edit_reason
                    })
                punches.append(HistoryPunch(**punch_data))

            if abono and abono.amount_hours:
                worked_seconds += (abono.amount_hours * 3600)

            total_worked_seconds += worked_seconds

            day_name = self._get_day_name(current)
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

            history_days.append(HistoryDay(
                date=current,
                day_name=day_name,
                is_holiday=bool(holiday),
                is_weekend=is_weekend,
                is_absent=(status == "Falta"),
                status=status,
                holiday_name=holiday.name if holiday else None,
                worked_time=worked_time_str,
                punches=punches,
                has_anomaly=len(day_anomalies) > 0,
                anomalies=[a.description for a in day_anomalies],
                abono_hours=abono.amount_hours if abono else None,
                abono_id=abono.id if abono and is_manager else None
            ))
            current += timedelta(days=1)

        total_month_minutes = int(round(total_worked_seconds / 60))
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

        has_schedule = bool(user.schedules)

        tz = ZoneInfo(settings.TIMEZONE)
        today_date = datetime.now(tz).date()

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        all_records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(db, month, year)
        approved_adjustments = adjustment_repository.get_approved_by_range(db, user_id, start_date, end_date)

        daily_details = []

        total_worked_seconds = 0.0
        total_expected_seconds = 0.0

        total_extra_hours = 0.0
        total_missing_hours = 0.0

        days_worked_count = 0
        absences_count = 0

        is_maintainer = current_user is not None and current_user.role == UserRole.MAINTAINER

        current = start_date
        while current <= end_date:
            is_future = current > today_date
            is_today = current == today_date

            day_records = [r for r in all_records if r.record_datetime.date() == current]
            day_records.sort(key=lambda x: x.record_datetime)

            is_holiday = any(h.date == current for h in holidays)

            adjustment_day = next((adj for adj in approved_adjustments
                                   if adj.target_date == current
                                   and adj.adjustment_type == AdjustmentType.WAIVER),
                                  None)

            is_waiver = adjustment_day is not None
            adj_id = adjustment_day.id if adjustment_day else None
            is_excused = is_waiver

            weekday = current.weekday()
            is_weekend = weekday >= 5

            expected_seconds = 0.0
            if has_schedule and not is_holiday and not is_future:
                schedule = next((s for s in user.schedules if s.day_of_week == weekday), None)
                if schedule:
                    expected_seconds = schedule.daily_hours * 3600

            entries = []
            exits = []
            punches = []
            detailed_punches = []
            worked_seconds = 0.0
            entry_time = None

            for rec in day_records:
                time_str = rec.record_datetime.strftime("%H:%M")
                suffix = "(E)" if rec.record_type == RecordType.ENTRY else "(S)"
                punches.append(f"{time_str} {suffix}")

                if is_maintainer:
                    detailed_punches.append(PunchDetail(
                        id=rec.id,
                        time=rec.record_datetime.strftime("%H:%M:%S"),
                        record_type=rec.record_type.value,
                        ip_address=rec.ip_address,
                        device_name=rec.device_name,
                        platform=rec.platform,
                        biometric_id=rec.biometric_id,
                        edited_by=rec.edited_by,
                        edit_justification=rec.edit_justification.value if rec.edit_justification else None,
                        edit_reason=rec.edit_reason
                    ))

                if rec.record_type == RecordType.ENTRY:
                    entries.append(time_str)
                    entry_time = rec.record_datetime
                elif rec.record_type == RecordType.EXIT:
                    exits.append(time_str)
                    if entry_time:
                        delta = rec.record_datetime - entry_time
                        seconds = delta.total_seconds()
                        if seconds <= 86400:
                            worked_seconds += seconds
                        entry_time = None

            waiver_credit = 0.0
            if is_excused:
                if adjustment_day.amount_hours and adjustment_day.amount_hours > 0:
                    waiver_credit = adjustment_day.amount_hours * 3600
                else:
                    if expected_seconds > 0 and worked_seconds < expected_seconds:
                        waiver_credit = expected_seconds - worked_seconds
                worked_seconds += waiver_credit

            if worked_seconds > 0:
                days_worked_count += 1

            if worked_seconds == 0 and expected_seconds > 0 and not is_weekend and not is_holiday and not is_excused and not is_future and not is_today:
                absences_count += 1

            day_worked_hours = worked_seconds / 3600.0
            day_expected_hours = expected_seconds / 3600.0

            day_balance = 0.0
            if has_schedule:
                day_balance = day_worked_hours - day_expected_hours

            day_extra = day_balance if day_balance > 0 else 0.0
            day_missing = abs(day_balance) if day_balance < 0 else 0.0

            total_worked_seconds += worked_seconds
            total_expected_seconds += expected_seconds

            total_extra_hours += day_extra
            total_missing_hours += day_missing

            status = "Normal"
            if is_future:
                status = ""
            elif is_waiver:
                formatted_waiver = self._format_duration(waiver_credit)
                status = f"Abonado/Atestado ({formatted_waiver})"
            elif is_holiday:
                status = "Feriado"
            elif is_weekend:
                if worked_seconds > 0:
                    status = "Normal"
                else:
                    status = "Fim de Semana"
            elif worked_seconds == 0 and expected_seconds > 0:
                if is_today:
                    status = ""
                else:
                    status = "Falta"
            elif not has_schedule and worked_seconds == 0:
                status = "-"

            worked_minutes_int = int(round(worked_seconds / 60))

            daily_details.append(DailyReportItem(
                date=current,
                day_name=self._get_day_name(current),
                is_holiday=is_holiday,
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
                expected_time=self._format_duration(expected_seconds)
            ))

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
        query = db.query(User)
        query = self._apply_employee_filters(query, employee_ids)
        users = query.all()

        payroll_data = []
        for user in users:
            report = self.get_advanced_user_report(db, user.id, month, year, current_user)
            if report and report.summary.total_worked_minutes > 0:
                payroll_data.append(report.summary)
        return MonthlyReportResponse(month=month, year=year, payroll_data=payroll_data)


report_service = ReportService()
