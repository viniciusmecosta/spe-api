from datetime import date, timedelta, datetime
import pytz
from calendar import monthrange
from sqlalchemy.orm import Session
from app.core.config import settings
from app.repositories.user_repository import user_repository
from app.repositories.time_record_repository import time_record_repository
from app.domain.models.enums import RecordType
from app.schemas.report import MonthlyReportResponse, MonthlySummaryItem, UserReportResponse, DailyReportItem
from app.services.work_hour_service import work_hour_service


class ReportService:
    def _get_month_range(self, month: int, year: int):
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        return start_date, end_date

    def get_monthly_summary(self, db: Session, month: int, year: int) -> MonthlyReportResponse:
        start_date, end_date = self._get_month_range(month, year)
        users = user_repository.get_multi(db, limit=1000)  # Assumindo limite razoável para o MVP

        summary_items = []
        for user in users:
            # Reutiliza o serviço de banco de horas para calcular totais
            balance_data = work_hour_service.calculate_balance(db, user.id, start_date, end_date)

            summary_items.append(MonthlySummaryItem(
                user_id=user.id,
                user_name=user.name,
                total_worked_hours=balance_data.total_worked_hours,
                expected_hours=balance_data.expected_hours,
                balance_hours=balance_data.balance_hours
            ))

        return MonthlyReportResponse(
            month=month,
            year=year,
            employees=summary_items
        )

    def get_user_report(self, db: Session, user_id: int, month: int, year: int) -> UserReportResponse:
        start_date, end_date = self._get_month_range(month, year)
        user = user_repository.get(db, user_id)
        if not user:
            return None  # Ou raise HTTPException

        tz = pytz.timezone(settings.TIMEZONE)
        start_dt = tz.localize(datetime.combine(start_date, datetime.min.time()))
        end_dt = tz.localize(datetime.combine(end_date, datetime.max.time()))

        records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)

        # Agrupar registros por dia
        daily_records = {}
        current = start_date
        while current <= end_date:
            daily_records[current] = []
            current += timedelta(days=1)

        for record in records:
            r_date = record.record_datetime.date()
            if r_date in daily_records:
                daily_records[r_date].append(record)

        daily_details = []
        daily_workload = user.weekly_workload_hours / 5.0

        total_worked_month = 0.0
        total_expected_month = 0.0

        for day, day_records in daily_records.items():
            entries = []
            exits = []
            day_worked_seconds = 0.0
            entry_time = None

            # Ordenar por horário para garantir pares corretos
            day_records.sort(key=lambda x: x.record_datetime)

            for rec in day_records:
                time_str = rec.record_datetime.strftime("%H:%M")
                if rec.record_type == RecordType.ENTRY:
                    entries.append(time_str)
                    entry_time = rec.record_datetime
                elif rec.record_type == RecordType.EXIT:
                    exits.append(time_str)
                    if entry_time:
                        delta = rec.record_datetime - entry_time
                        day_worked_seconds += delta.total_seconds()
                        entry_time = None

            day_worked_hours = day_worked_seconds / 3600.0

            # Cálculo de horas esperadas (apenas dias úteis)
            day_expected = daily_workload if day.weekday() < 5 else 0.0
            day_balance = day_worked_hours - day_expected

            total_worked_month += day_worked_hours
            total_expected_month += day_expected

            daily_details.append(DailyReportItem(
                date=day,
                entries=entries,
                exits=exits,
                worked_hours=round(day_worked_hours, 2),
                balance_hours=round(day_balance, 2)
            ))

        return UserReportResponse(
            user_id=user.id,
            user_name=user.name,
            month=month,
            year=year,
            total_worked_hours=round(total_worked_month, 2),
            expected_hours=round(total_expected_month, 2),
            total_balance_hours=round(total_worked_month - total_expected_month, 2),
            daily_details=daily_details
        )


report_service = ReportService()