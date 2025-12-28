import locale
from calendar import monthrange
from datetime import date, timedelta, datetime
from io import BytesIO
from typing import List

import pytz
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter  # Importação necessária
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
    DailyReportItem, DashboardMetricsResponse
)

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

    def _get_day_name(self, dt: date) -> str:
        days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        return days[dt.weekday()]

    def get_dashboard_metrics(self, db: Session) -> DashboardMetricsResponse:
        tz = pytz.timezone(settings.TIMEZONE)
        today = datetime.now(tz).date()

        active_users = db.query(User).filter(
            User.is_active == True,
            User.role == UserRole.EMPLOYEE
        ).count()

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

    def get_advanced_user_report(self, db: Session, user_id: int, month: int, year: int) -> AdvancedUserReportResponse:
        start_date, end_date = self._get_month_range(month, year)
        user = user_repository.get(db, user_id)
        if not user:
            return None

        tz = pytz.timezone(settings.TIMEZONE)
        start_dt = tz.localize(datetime.combine(start_date, datetime.min.time()))
        end_dt = tz.localize(datetime.combine(end_date, datetime.max.time()))

        all_records = time_record_repository.get_by_range(db, user_id, start_dt, end_dt)
        holidays = holiday_repository.get_by_month(db, month, year)
        approved_adjustments = adjustment_repository.get_approved_by_range(db, user_id, start_date, end_date)

        daily_details = []

        total_worked = 0.0
        total_expected = 0.0
        total_extra = 0.0
        total_missing = 0.0
        days_worked_count = 0
        absences_count = 0

        current = start_date
        while current <= end_date:
            day_records = [r for r in all_records if r.record_datetime.date() == current]
            day_records.sort(key=lambda x: x.record_datetime)

            is_holiday = any(h.date == current for h in holidays)

            certificate_adj = next((adj for adj in approved_adjustments
                                    if
                                    adj.target_date == current and adj.adjustment_type == AdjustmentType.CERTIFICATE),
                                   None)
            is_certificate = certificate_adj is not None

            weekday = current.weekday()
            is_weekend = weekday >= 5

            schedule = next((s for s in user.work_schedules if s.day_of_week == weekday), None)
            expected = schedule.daily_hours if schedule and not is_holiday and not is_certificate else 0.0

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

            if day_worked > 0:
                days_worked_count += 1

            balance = day_worked - expected

            day_extra = balance if balance > 0 else 0.0
            day_missing = abs(balance) if balance < 0 else 0.0

            if balance < 0 and not is_holiday and not is_weekend and not is_certificate:
                absences_count += 1

            total_worked += day_worked
            total_expected += expected
            total_extra += day_extra
            total_missing += day_missing

            status = "Normal"
            if is_certificate:
                status = "Atestado/Abono"
            elif is_holiday:
                status = "Feriado"
            elif is_weekend:
                status = "Fim de Semana"
            elif day_worked == 0 and expected > 0:
                status = "Falta"
            elif day_worked > expected:
                status = "Hora Extra"

            daily_details.append(DailyReportItem(
                date=current,
                day_name=self._get_day_name(current),
                is_holiday=is_holiday,
                is_weekend=is_weekend,
                status=status,
                entries=entries,
                exits=exits,
                worked_hours=round(day_worked, 2),
                expected_hours=round(expected, 2),
                balance_hours=round(balance, 2),
                extra_hours=round(day_extra, 2),
                missing_hours=round(day_missing, 2)
            ))

            current += timedelta(days=1)

        summary = UserPayrollSummary(
            user_id=user.id,
            user_name=user.name,
            total_worked_hours=round(total_worked, 2),
            total_expected_hours=round(total_expected, 2),
            total_extra_hours=round(total_extra, 2),
            total_missing_hours=round(total_missing, 2),
            final_balance=round(total_worked - total_expected, 2),
            days_worked=days_worked_count,
            absences=absences_count
        )

        return AdvancedUserReportResponse(summary=summary, daily_details=daily_details)

    def get_monthly_summary(self, db: Session, month: int, year: int,
                            employee_ids: List[int] = None) -> MonthlyReportResponse:
        query = db.query(User).filter(
            User.is_active == True,
            User.role == UserRole.EMPLOYEE
        )

        if employee_ids:
            query = query.filter(User.id.in_(employee_ids))

        users = query.all()
        payroll_data = []

        for user in users:
            report = self.get_advanced_user_report(db, user.id, month, year)
            if report:
                payroll_data.append(report.summary)

        return MonthlyReportResponse(month=month, year=year, payroll_data=payroll_data)

    def generate_excel_report(self, db: Session, month: int, year: int, employee_ids: List[int] = None) -> BytesIO:
        query = db.query(User).filter(
            User.is_active == True,
            User.role == UserRole.EMPLOYEE
        )
        if employee_ids:
            query = query.filter(User.id.in_(employee_ids))
        users = query.all()

        wb = Workbook()

        ws_summary = wb.active
        ws_summary.title = "Resumo Folha"

        headers_sum = [
            "ID", "Funcionário", "Dias Trabalhados", "Faltas Reais",
            "Horas Normais", "Horas Extras", "Horas Faltantes", "Saldo Final"
        ]
        ws_summary.append(headers_sum)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'),
                        bottom=Side(style='thin'))

        for col_num, header in enumerate(headers_sum, 1):
            cell = ws_summary.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

        for user in users:
            report = self.get_advanced_user_report(db, user.id, month, year)
            sum_data = report.summary
            ws_summary.append([
                sum_data.user_id,
                sum_data.user_name,
                sum_data.days_worked,
                sum_data.absences,
                sum_data.total_expected_hours,
                sum_data.total_extra_hours,
                sum_data.total_missing_hours,
                sum_data.final_balance
            ])

        for col in ws_summary.columns:
            max_length = 0
            column = col[0].column_letter  # This works for standard cells
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws_summary.column_dimensions[column].width = max_length + 2

        for user in users:
            report = self.get_advanced_user_report(db, user.id, month, year)
            if not report: continue

            sheet_name = f"{user.id}-{user.name.split()[0]}"
            ws_det = wb.create_sheet(title=sheet_name[:30])

            ws_det.merge_cells('A1:J1')
            title_cell = ws_det['A1']
            title_cell.value = f"Folha de Ponto: {user.name} - {month}/{year}"
            title_cell.font = Font(size=14, bold=True)
            title_cell.alignment = Alignment(horizontal='center')

            headers_det = ["Data", "Dia Semana", "Status", "Entrada 1", "Saída 1", "Entrada 2", "Saída 2", "Trabalhado",
                           "Previsto", "Saldo"]
            ws_det.append(headers_det)

            for col_num, header in enumerate(headers_det, 1):
                cell = ws_det.cell(row=2, column=col_num)
                cell.font = header_font
                cell.fill = header_fill
                cell.border = border

            for day in report.daily_details:
                e1 = day.entries[0] if len(day.entries) > 0 else ""
                s1 = day.exits[0] if len(day.exits) > 0 else ""
                e2 = day.entries[1] if len(day.entries) > 1 else ""
                s2 = day.exits[1] if len(day.exits) > 1 else ""

                if len(day.entries) > 2: e2 += " ..."

                row_data = [
                    day.date.strftime("%d/%m/%Y"),
                    day.day_name,
                    day.status,
                    e1, s1, e2, s2,
                    day.worked_hours,
                    day.expected_hours,
                    day.balance_hours
                ]
                ws_det.append(row_data)

                last_row = ws_det.max_row
                status_cell = ws_det.cell(row=last_row, column=3)
                if day.status == "Falta":
                    status_cell.font = Font(color="FF0000", bold=True)
                elif "Atestado" in day.status:
                    status_cell.font = Font(color="008000", bold=True)
                elif day.status == "Feriado":
                    status_cell.font = Font(color="0000FF", bold=True)
                elif day.status == "Fim de Semana":
                    for col in range(1, 11):
                        ws_det.cell(row=last_row, column=col).fill = PatternFill(start_color="E0E0E0",
                                                                                 end_color="E0E0E0", fill_type="solid")

            ws_det.append([])
            ws_det.append(["TOTAIS", "", "", "", "", "", "",
                           report.summary.total_worked_hours,
                           report.summary.total_expected_hours,
                           report.summary.final_balance])

            for col in range(1, 11):
                ws_det.cell(row=ws_det.max_row, column=col).font = Font(bold=True)

            for i in range(1, 11):
                col_letter = get_column_letter(i)
                ws_det.column_dimensions[col_letter].width = 15

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output


report_service = ReportService()
