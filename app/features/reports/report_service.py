import locale
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import extract
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.holidays.holiday_repository import holiday_repository
from app.features.payroll.payroll_models import PayrollClosure
from app.features.reports.report_schemas import (
    AdvancedUserReportResponse,
    DailyReportItem,
    HistoryDay,
    HistoryPunch,
    HistoryResponse,
    MonthlyReportResponse,
    PunchDetail,
    UserPayrollSummary,
)
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_repository import (
    time_record_repository,
)
from app.features.timesheets.anomaly_service import anomaly_service
from app.features.users.user_models import User
from app.features.users.user_repository import user_repository
from app.shared import time_calculation_service as time_calc_mod
from app.shared.enums import AdjustmentStatus, DayOfWeek, UserRole

logger = logging.getLogger(__name__)

WEEKEND_STATUS = "Fim de semana"

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except locale.Error:
    pass


class ReportService:
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

    def _build_history_day(
            self,
            current: date,
            today_date: date,
            records: list[TimeRecord],
            holidays: list,
            anomalies: list,
            period_result,
            is_manager: bool
    ) -> HistoryDay:
        day_records = [r for r in records if r.record_datetime.date() == current]
        day_records.sort(key=lambda x: x.record_datetime)

        holiday = next((h for h in holidays if h.date == current), None)

        day_anomalies = [a for a in anomalies if a.date == current]

        daily_res = period_result.daily_results[current]
        worked_seconds = daily_res.net_worked_seconds
        abono = period_result.daily_waivers[current]

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
            punches=punches,
            has_anomaly=len(anomalies_list) > 0,
            anomalies=anomalies_list,
            abono_hours=abono.amount_hours if abono else None,
            abono_id=abono.id if abono and is_manager else None
        )

    def _build_detailed_punches(self, day_records: list[TimeRecord], is_maintainer: bool) -> list[PunchDetail]:
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
                return WEEKEND_STATUS
            return ""
        if is_waiver:
            return "Abono"
        if is_holiday:
            return "Feriado"
        if is_weekend:
            if worked_seconds > 0:
                return "Normal"
            return WEEKEND_STATUS
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
            all_records: list[TimeRecord],
            holidays: list,
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

        target_day = DayOfWeek(current.weekday())
        is_weekend = target_day in (DayOfWeek.SABADO, DayOfWeek.DOMINGO)

        expected_seconds = period_result.daily_expected_seconds[current]

        worked_seconds = daily_res.net_worked_seconds
        unapproved_extra_seconds = daily_res.unapproved_extra_seconds
        entries = daily_res.entries
        exits = daily_res.exits
        punches = daily_res.punches

        detailed_punches = self._build_detailed_punches(day_records, is_maintainer)

        day_worked_hours = worked_seconds / 3600.0
        day_expected_hours = expected_seconds / 3600.0

        day_extra = daily_res.extra_seconds / 3600.0
        day_missing = daily_res.missing_seconds / 3600.0
        day_balance = day_extra - day_missing

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
            day_name=DayOfWeek(current.weekday()).abreviado,
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

    def get_history_report(self, db: Session, user_id: int, month: int | None, year: int | None,
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
            end_date = min(end_date, now.date())
        elif datetime(year, month, 1).date() > now.date():
            return HistoryResponse(month=month, year=year, total_worked_time="00:00", days=[])

        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(db, month, year)

        ignore_excessive = (current_user.id == user_id)
        anomalies = anomaly_service.get_anomalies(db, start_date, end_date, user_id,
                                                  ignore_excessive_hours=ignore_excessive)

        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]

        all_adjustments = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id == user_id,
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.deleted_at.is_(None)
        ).all()

        history_days = []

        period_result = time_calc_mod.time_calculation_service.calculate_period_time(
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

    def _fetch_report_data(self, db: Session, user_id: int, month: int, year: int,
                           start_dt: datetime, end_dt: datetime,
                           prefetched_records, prefetched_adjustments, prefetched_holidays):
        if prefetched_records is not None:
            all_records = prefetched_records
        else:
            all_records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)

        if prefetched_holidays is not None:
            holidays = prefetched_holidays
        else:
            holidays = holiday_repository.get_by_month(db, month, year)

        if prefetched_adjustments is not None:
            all_adjustments = prefetched_adjustments
        else:
            all_adjustments = db.query(AdjustmentRequest).filter(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date >= start_dt.date(),
                AdjustmentRequest.target_date <= end_dt.date(),
                AdjustmentRequest.deleted_at.is_(None)
            ).all()
        return all_records, all_adjustments, holidays

    def get_advanced_user_report(self, db: Session, user_id: int, month: int, year: int,
                                 current_user: User | None = None,
                                 prefetched_records: list[TimeRecord] | None = None,
                                 prefetched_adjustments: list | None = None,
                                 prefetched_holidays: list | None = None) -> AdvancedUserReportResponse | None:
        start_date, end_date = self._get_month_range(month, year)
        user = user_repository.get(db, user_id)
        if not user:
            return None

        has_schedule = bool(user.historical_schedules)
        tz = ZoneInfo(settings.TIMEZONE)
        today_date = datetime.now(tz).date()

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        all_records, all_adjustments, holidays = self._fetch_report_data(
            db, user_id, month, year, start_dt, end_dt,
            prefetched_records, prefetched_adjustments, prefetched_holidays
        )

        daily_details = []
        days_worked_count = 0
        absences_count = 0

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
                            employee_ids: list[int] | None = None,
                            current_user: User | None = None) -> MonthlyReportResponse:
        query = db.query(User).options(joinedload(User.historical_schedules))
        query = self._apply_employee_filters(query, employee_ids)
        users = query.all()

        user_ids = [u.id for u in users]
        start_date, end_date = self._get_month_range(month, year)
        tz = ZoneInfo(settings.TIMEZONE)
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        all_records_batch = db.query(TimeRecord).filter(
            TimeRecord.user_id.in_(user_ids),
            TimeRecord.record_datetime >= start_dt,
            TimeRecord.record_datetime <= end_dt,
            TimeRecord.deleted_at.is_(None),
            TimeRecord.is_ignored == False
        ).all() if user_ids else []
        records_by_user = {}
        for r in all_records_batch:
            records_by_user.setdefault(r.user_id, []).append(r)

        all_adjustments_batch = db.query(AdjustmentRequest).filter(
            AdjustmentRequest.user_id.in_(user_ids),
            AdjustmentRequest.target_date >= start_date,
            AdjustmentRequest.target_date <= end_date,
            AdjustmentRequest.deleted_at.is_(None)
        ).all() if user_ids else []
        adjustments_by_user = {}
        for a in all_adjustments_batch:
            adjustments_by_user.setdefault(a.user_id, []).append(a)

        holidays_batch = holiday_repository.get_by_month(db, month, year)

        payroll_data = []
        for user in users:
            report = self.get_advanced_user_report(
                db, user.id, month, year, current_user,
                prefetched_records=records_by_user.get(user.id, []),
                prefetched_adjustments=adjustments_by_user.get(user.id, []),
                prefetched_holidays=holidays_batch
            )
            if report and report.summary.total_worked_minutes > 0:
                payroll_data.append(report.summary)

        return MonthlyReportResponse(month=month, year=year, payroll_data=payroll_data)

    def check_report_permission(self, current_user: User) -> None:
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if not is_manager and not current_user.can_export_report:
            raise HTTPException(
                status_code=403,
                detail="O usuário não possui privilégios suficientes para acessar relatórios globais.",
            )

    def check_user_report_access(self, current_user: User, user_id: int,
                                 detail: str = "Sem permissão para acessar o histórico deste usuário.") -> None:
        is_manager = current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]
        if not is_manager and not current_user.can_export_report and current_user.id != user_id:
            raise HTTPException(
                status_code=403,
                detail=detail,
            )

    def get_advanced_user_report_or_404(
            self, db: Session, user_id: int, month: int, year: int, current_user: User
    ) -> AdvancedUserReportResponse:
        report = self.get_advanced_user_report(db, user_id, month, year, current_user)
        if not report:
            raise HTTPException(status_code=404, detail="User not found or data missing")
        return report

    def validate_excel_export_permission(
            self, db: Session, current_user: User, month: int, year: int, now: datetime
    ) -> None:
        is_maintainer = current_user.role == UserRole.MAINTAINER
        is_manager = current_user.role == UserRole.MANAGER

        if is_maintainer:
            return

        if is_manager:
            pending_adjustments = db.query(AdjustmentRequest).filter(
                AdjustmentRequest.status == AdjustmentStatus.PENDING,
                extract("month", AdjustmentRequest.target_date) == month,
                extract("year", AdjustmentRequest.target_date) == year,
            ).first()

            if pending_adjustments:
                raise HTTPException(
                    status_code=400,
                    detail="Não é possível gerar o relatório pois existem ajustes pendentes neste mês.",
                )
            return

        if not current_user.can_export_report:
            raise HTTPException(
                status_code=403, detail="Você não tem permissão para gerar relatórios."
            )

        prev_month = now.month - 1 if now.month > 1 else 12
        prev_year = now.year if now.month > 1 else now.year - 1

        if month != prev_month or year != prev_year:
            raise HTTPException(
                status_code=400,
                detail="Funcionários só podem gerar o relatório referente ao mês anterior.",
            )

        payroll_closed = db.query(PayrollClosure).filter(
            PayrollClosure.month == month,
            PayrollClosure.year == year,
            PayrollClosure.is_closed == True,
            PayrollClosure.deleted_at.is_(None),
        ).first()

        if not payroll_closed:
            raise HTTPException(
                status_code=400,
                detail="Não é possível gerar o relatório pois a folha deste mês ainda não está fechada.",
            )


report_service = ReportService()
