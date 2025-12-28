import locale
from calendar import monthrange
from datetime import date, timedelta, datetime
from io import BytesIO

import pytz
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.enums import RecordType
from app.repositories.adjustment_repository import adjustment_repository
from app.repositories.holiday_repository import holiday_repository
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.report import MonthlyReportResponse, MonthlySummaryItem, UserReportResponse, DailyReportItem, \
    DashboardMetricsResponse

# Tenta setar locale para PT-BR para nomes dos dias, fallback para inglês se não disponível no sistema
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except:
    pass


class ReportService:
    def _get_month_range(self, month: int, year: int):
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        return start_date, end_date

    def _get_day_status_and_hours(self, db: Session, user, current_date: date, holidays: list, records: list):
        # 1. Verifica Feriado
        is_holiday = any(h.date == current_date for h in holidays)
        if is_holiday:
            return "Feriado", 0.0

        # 2. Verifica Configuração de Horário do Usuário para o dia da semana
        weekday = current_date.weekday()  # 0=Segunda, 6=Domingo
        schedule = next((s for s in user.work_schedules if s.day_of_week == weekday), None)

        expected_hours = schedule.daily_hours if schedule else 0.0

        # 3. Verifica Registros
        has_records = len(records) > 0

        # Lógica de Status
        status = "Normal"

        if not has_records:
            if expected_hours == 0:
                if weekday == 5:
                    status = "Sábado"
                elif weekday == 6:
                    status = "Domingo"
                else:
                    status = "Folga"
            else:
                status = "Falta"
        else:
            status = "Trabalhado"
            # Se trabalhou em feriado ou folga
            if expected_hours == 0:
                status = "Trabalho Extra/Folga"

        return status, expected_hours

    def get_dashboard_metrics(self, db: Session) -> DashboardMetricsResponse:
        tz = pytz.timezone(settings.TIMEZONE)
        today = datetime.now(tz).date()

        active_users = user_repository.count_active(db)
        pending = adjustment_repository.count_pending(db)

        today_start = tz.localize(datetime.combine(today, datetime.min.time()))
        today_end = tz.localize(datetime.combine(today, datetime.max.time()))

        present = time_record_repository.count_unique_users_in_range(db, today_start, today_end)

        return DashboardMetricsResponse(
            total_active_employees=active_users,
            pending_adjustments=pending,
            employees_present_today=present,
            date=today
        )

    def get_user_report(self, db: Session, user_id: int, month: int, year: int) -> UserReportResponse:
        start_date, end_date = self._get_month_range(month, year)
        user = user_repository.get(db, user_id)
        if not user:
            return None

        tz = pytz.timezone(settings.TIMEZONE)
        # Buscar todos os registros do mês
        start_dt = tz.localize(datetime.combine(start_date, datetime.min.time()))
        end_dt = tz.localize(datetime.combine(end_date, datetime.max.time()))

        all_records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(db, month, year)

        daily_details = []

        total_worked = 0.0
        total_expected = 0.0

        # Iterar dia a dia do mês
        current = start_date
        while current <= end_date:
            # Filtra registros do dia atual
            day_records = [r for r in all_records if r.record_datetime.date() == current]
            day_records.sort(key=lambda x: x.record_datetime)

            status, expected = self._get_day_status_and_hours(db, user, current, holidays, day_records)

            # Calcular horas trabalhadas no dia
            entries = []
            exits = []
            worked_seconds = 0.0
            entry_time = None

            for rec in day_records:
                time_str = rec.record_datetime.strftime("%H:%M")
                if rec.record_type == RecordType.ENTRY:
                    entries.append(time_str)
                    entry_time = rec.record_datetime
                elif rec.record_type == RecordType.EXIT:
                    exits.append(time_str)
                    if entry_time:
                        delta = rec.record_datetime - entry_time
                        worked_seconds += delta.total_seconds()
                        entry_time = None

            day_worked = worked_seconds / 3600.0

            # Banco de horas só computa se houver expectativa cadastrada OU se trabalhou sem expectativa
            # Se expected == 0 e worked == 0, balance = 0
            day_balance = day_worked - expected

            total_worked += day_worked
            total_expected += expected

            # Tradução simples do dia da semana se locale falhar
            week_days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
            day_name_str = week_days[current.weekday()]

            daily_details.append(DailyReportItem(
                date=current,
                day_name=day_name_str,
                status=status,
                entries=entries,
                exits=exits,
                worked_hours=round(day_worked, 2),
                expected_hours=round(expected, 2),
                balance_hours=round(day_balance, 2)
            ))

            current += timedelta(days=1)

        return UserReportResponse(
            user_id=user.id,
            user_name=user.name,
            month=month,
            year=year,
            total_worked_hours=round(total_worked, 2),
            expected_hours=round(total_expected, 2),
            total_balance_hours=round(total_worked - total_expected, 2),
            daily_details=daily_details
        )

    def get_monthly_summary(self, db: Session, month: int, year: int) -> MonthlyReportResponse:
        users = user_repository.get_active_users(db)
        summary_items = []

        for user in users:
            report = self.get_user_report(db, user.id, month, year)
            summary_items.append(MonthlySummaryItem(
                user_id=user.id,
                user_name=user.name,
                total_worked_hours=report.total_worked_hours,
                expected_hours=report.expected_hours,
                balance_hours=report.total_balance_hours
            ))

        return MonthlyReportResponse(month=month, year=year, employees=summary_items)

    def generate_excel_report(self, db: Session, month: int, year: int) -> BytesIO:
        users = user_repository.get_active_users(db)

        wb = Workbook()
        ws = wb.active
        ws.title = "Resumo"

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")

        ws.append(["ID", "Nome", "Trabalhado", "Esperado", "Saldo"])
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill

        ws_det = wb.create_sheet("Detalhado")
        headers_det = ["ID", "Nome", "Data", "Dia", "Status", "Entradas", "Saídas", "Trabalhado", "Esperado", "Saldo"]
        ws_det.append(headers_det)
        for cell in ws_det[1]:
            cell.font = header_font
            cell.fill = header_fill

        for user in users:
            report = self.get_user_report(db, user.id, month, year)

            ws.append(
                [user.id, user.name, report.total_worked_hours, report.expected_hours, report.total_balance_hours])

            # Detalhe
            for day in report.daily_details:
                ws_det.append([
                    user.id,
                    user.name,
                    day.date,
                    day.day_name,
                    day.status,
                    ", ".join(day.entries),
                    ", ".join(day.exits),
                    day.worked_hours,
                    day.expected_hours,
                    day.balance_hours
                ])

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output


report_service = ReportService()
