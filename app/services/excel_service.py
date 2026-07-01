import os
import re
from io import BytesIO
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.domain.models.user import User
from app.repositories.company_repository import company_repository
from app.services.report_service import report_service


class ExcelService:
    def __init__(self):
        self._setup_styles()

    def _setup_styles(self):
        self.header_font = Font(bold=True, color="FFFFFF")
        self.header_fill = PatternFill(start_color="475569", end_color="475569", fill_type="solid")
        self.border_bottom = Border(bottom=Side(style='thin', color="CBD5E1"))
        
        self.fill_weekend = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        self.fill_holiday = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
        self.fill_absence = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        self.fill_excused = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        
        self.font_absence = Font(color="991B1B", bold=True)
        self.font_excused = Font(color="166534", bold=True)
        self.font_holiday = Font(color="92400E", bold=True)
        
        self.align_center = Alignment(horizontal='center', vertical='center')

    def _format_cnpj(self, cnpj: str) -> str:
        if not cnpj: return "-"
        c = re.sub(r'[^0-9]', '', cnpj)
        if len(c) == 14:
            return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
        return cnpj

    def _get_month_name(self, month: int) -> str:
        months = {
            1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
            5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
            9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
        }
        return months.get(month, "")

    def _time_str_to_fraction(self, time_str: str) -> float:
        if not time_str or ":" not in time_str:
            return 0.0
        parts = time_str.split(":")
        if len(parts) >= 2:
            try:
                hours = int(parts[0])
                minutes = int(parts[1])
                return (hours + (minutes / 60.0)) / 24.0
            except ValueError:
                return 0.0
        return 0.0

    def generate_excel_report(self, db: Session, month: int, year: int, employee_ids: Optional[List[int]] = None,
                              current_user: Optional[User] = None) -> BytesIO:
        query = db.query(User).options(joinedload(User.schedules))
        query = report_service._apply_employee_filters(query, employee_ids)
        users = query.all()

        company = company_repository.get_current(db)
        company_name = company.name if company else "Empresa Não Cadastrada"
        company_cnpj = self._format_cnpj(company.cnpj if company else "")

        logo_path = None
        if company and company.logo_path:
            full_logo_path = os.path.join(settings.UPLOAD_DIR, company.logo_path)
            if os.path.exists(full_logo_path):
                logo_path = full_logo_path

        user_reports = []
        for user in users:
            report = report_service.get_advanced_user_report(db, user.id, month, year, current_user)
            if report and report.summary.total_worked_minutes > 0:
                user_reports.append((user, report))

        wb = Workbook()
        
        self._build_summary_sheet(wb, month, year, user_reports, company_name, company_cnpj, logo_path)
        
        for user, report in user_reports:
            self._build_employee_sheet(wb, user, report, month, year, company_name, company_cnpj, logo_path)
            
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    def _insert_header_and_logo(self, ws, title_text: str, subtitle_text: str, company_name: str, company_cnpj: str, logo_path: Optional[str], end_col: str):
        ws.merge_cells(f'A1:{end_col}1')
        ws['A1'].value = company_name
        ws['A1'].font = Font(size=14, bold=True)
        ws['A1'].alignment = self.align_center

        ws.merge_cells(f'A2:{end_col}2')
        ws['A2'].value = f"CNPJ: {company_cnpj}"
        ws['A2'].alignment = self.align_center

        ws.merge_cells(f'A3:{end_col}3')
        ws['A3'].value = title_text
        ws['A3'].font = Font(size=12, bold=True)
        ws['A3'].alignment = self.align_center

        if subtitle_text:
            ws.merge_cells(f'A4:{end_col}4')
            ws['A4'].value = subtitle_text
            ws['A4'].font = Font(size=11, bold=True, color="334155")
            ws['A4'].alignment = self.align_center

        if logo_path:
            try:
                img = OpenpyxlImage(logo_path)
                img.width = 60
                img.height = 60
                ws.add_image(img, 'A1')
                ws.row_dimensions[1].height = 50
            except Exception:
                pass
        ws.append([])

    def _build_summary_sheet(self, wb, month, year, user_reports, company_name, company_cnpj, logo_path):
        ws_summary = wb.active
        ws_summary.title = "Resumo Folha"

        subtitle = f"{self._get_month_name(month)} DE {year}"
        self._insert_header_and_logo(ws_summary, "Relatório de Gestão", subtitle, company_name, company_cnpj, logo_path, 'C')

        ws_summary.append(["* Nota: O formato de tempo exibido é HH:MM (Horas:Minutos)."])
        note_row1 = ws_summary.max_row
        ws_summary.merge_cells(start_row=note_row1, start_column=1, end_row=note_row1, end_column=3)
        ws_summary.cell(row=note_row1, column=1).font = Font(italic=True, color="64748B")
        
        ws_summary.append(["  Exemplo: 10:20 representa exatamente 10 horas e 20 minutos contabilizados."])
        note_row2 = ws_summary.max_row
        ws_summary.merge_cells(start_row=note_row2, start_column=1, end_row=note_row2, end_column=3)
        ws_summary.cell(row=note_row2, column=1).font = Font(italic=True, color="64748B")
        ws_summary.append([])

        headers_sum = ["Nome do Colaborador", "Dias Trabalhados", "Horas Trabalhadas"]
        ws_summary.append(headers_sum)
        header_row = ws_summary.max_row
        ws_summary.freeze_panes = f"A{header_row + 1}"

        for col_num, header in enumerate(headers_sum, 1):
            cell = ws_summary.cell(row=header_row, column=col_num)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.align_center
            cell.border = self.border_bottom

        for user, report in user_reports:
            sum_data = report.summary
            ws_summary.append([
                sum_data.user_name,
                sum_data.days_worked,
                self._time_str_to_fraction(sum_data.total_worked_time)
            ])
            
            last_row = ws_summary.max_row
            ws_summary.cell(row=last_row, column=1).border = self.border_bottom
            ws_summary.cell(row=last_row, column=2).border = self.border_bottom
            ws_summary.cell(row=last_row, column=2).alignment = self.align_center
            
            time_cell = ws_summary.cell(row=last_row, column=3)
            time_cell.border = self.border_bottom
            time_cell.alignment = self.align_center
            time_cell.number_format = '[h]:mm'

        ws_summary.column_dimensions['A'].width = 45
        ws_summary.column_dimensions['B'].width = 20
        ws_summary.column_dimensions['C'].width = 25

    def _build_employee_sheet(self, wb, user, report, month, year, company_name, company_cnpj, logo_path):
        sheet_name = f"{user.id}-{user.name.split()[0]}"[:30]
        ws_det = wb.create_sheet(title=sheet_name)

        subtitle = f"{self._get_month_name(month)} DE {year}"
        self._insert_header_and_logo(ws_det, f"Folha de Ponto: {user.name}", subtitle, company_name, company_cnpj, logo_path, 'F')

        ws_det.append(["* Nota: O formato de tempo exibido é HH:MM (Horas:Minutos)."])
        note_row1 = ws_det.max_row
        ws_det.merge_cells(start_row=note_row1, start_column=1, end_row=note_row1, end_column=6)
        ws_det.cell(row=note_row1, column=1).font = Font(italic=True, color="64748B")
        
        ws_det.append(["  Exemplo: 10:20 representa exatamente 10 horas e 20 minutos contabilizados."])
        note_row2 = ws_det.max_row
        ws_det.merge_cells(start_row=note_row2, start_column=1, end_row=note_row2, end_column=6)
        ws_det.cell(row=note_row2, column=1).font = Font(italic=True, color="64748B")
        ws_det.append([])

        ws_det.append(["Legenda de Cores de Status:"])
        legend_title_row = ws_det.max_row
        ws_det.merge_cells(start_row=legend_title_row, start_column=1, end_row=legend_title_row, end_column=6)
        ws_det.cell(row=legend_title_row, column=1).font = Font(bold=True, color="334155")
        
        ws_det.append(["", "Fim de Semana", "Feriado", "Falta", "Atestado/Abono", ""])
        legend_row = ws_det.max_row
        ws_det.cell(row=legend_row, column=2).fill = self.fill_weekend
        ws_det.cell(row=legend_row, column=2).alignment = self.align_center
        ws_det.cell(row=legend_row, column=2).border = self.border_bottom
        ws_det.cell(row=legend_row, column=3).fill = self.fill_holiday
        ws_det.cell(row=legend_row, column=3).font = self.font_holiday
        ws_det.cell(row=legend_row, column=3).alignment = self.align_center
        ws_det.cell(row=legend_row, column=3).border = self.border_bottom
        ws_det.cell(row=legend_row, column=4).fill = self.fill_absence
        ws_det.cell(row=legend_row, column=4).font = self.font_absence
        ws_det.cell(row=legend_row, column=4).alignment = self.align_center
        ws_det.cell(row=legend_row, column=4).border = self.border_bottom
        ws_det.cell(row=legend_row, column=5).fill = self.fill_excused
        ws_det.cell(row=legend_row, column=5).font = self.font_excused
        ws_det.cell(row=legend_row, column=5).alignment = self.align_center
        ws_det.cell(row=legend_row, column=5).border = self.border_bottom
        ws_det.append([])

        headers_det = ["Data", "Dia Semana", "Status", "Registros", "Trabalhado (Min)", "Trabalhado (Tempo)"]
        ws_det.append(headers_det)
        header_row = ws_det.max_row
        
        ws_det.freeze_panes = f"A{header_row + 1}"

        for col_num, header in enumerate(headers_det, 1):
            cell = ws_det.cell(row=header_row, column=col_num)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.border_bottom
            cell.alignment = self.align_center

        for day in report.daily_details:
            punches_str = " | ".join(day.punches)

            ws_det.append([
                day.date.strftime("%d/%m/%Y"),
                day.day_name,
                day.status,
                punches_str,
                day.worked_minutes,
                self._time_str_to_fraction(day.worked_time)
            ])
            last_row = ws_det.max_row

            for col in range(1, 7):
                c = ws_det.cell(row=last_row, column=col)
                c.border = self.border_bottom
                if col in [1, 2, 3, 5, 6]:
                    c.alignment = self.align_center

            ws_det.cell(row=last_row, column=6).number_format = '[h]:mm'

            status_cell = ws_det.cell(row=last_row, column=3)
            fill_to_apply = None

            if day.is_holiday:
                fill_to_apply = self.fill_holiday
                status_cell.font = self.font_holiday
            elif day.is_weekend:
                fill_to_apply = self.fill_weekend
            
            if "Falta" in day.status:
                fill_to_apply = self.fill_absence
                status_cell.font = self.font_absence
            elif "Atestado" in day.status or "Abonado" in day.status:
                fill_to_apply = self.fill_excused
                status_cell.font = self.font_excused

            if fill_to_apply:
                for col in range(1, 7):
                    ws_det.cell(row=last_row, column=col).fill = fill_to_apply

        ws_det.append([])
        ws_det.append(["TOTAIS", "", "", "",
                       report.summary.total_worked_minutes,
                       self._time_str_to_fraction(report.summary.total_worked_time)])
        last_row = ws_det.max_row

        for col in range(1, 7):
            cell = ws_det.cell(row=last_row, column=col)
            cell.font = Font(bold=True)
            cell.border = self.border_bottom
        ws_det.cell(row=last_row, column=5).alignment = self.align_center
        ws_det.cell(row=last_row, column=6).alignment = self.align_center
        ws_det.cell(row=last_row, column=6).number_format = '[h]:mm'

        ws_det.column_dimensions['A'].width = 12
        ws_det.column_dimensions['B'].width = 15
        ws_det.column_dimensions['C'].width = 25
        ws_det.column_dimensions['D'].width = 40
        ws_det.column_dimensions['E'].width = 18
        ws_det.column_dimensions['F'].width = 20

excel_service = ExcelService()
