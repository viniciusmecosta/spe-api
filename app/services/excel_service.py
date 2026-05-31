import os
import re
from io import BytesIO
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.user import User
from app.repositories.company_repository import company_repository
from app.services.report_service import report_service


class ExcelService:
    def _format_time_br(self, time_str: str) -> str:
        if not time_str or ":" not in time_str:
            return time_str
        parts = time_str.split(":")
        if len(parts) >= 2:
            return f"{parts[0]}h:{parts[1]}min"
        return time_str

    def _format_cnpj(self, cnpj: str) -> str:
        if not cnpj: return "-"
        c = re.sub(r'[^0-9]', '', cnpj)
        if len(c) == 14:
            return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
        return cnpj

    def generate_excel_report(self, db: Session, month: int, year: int, employee_ids: Optional[List[int]] = None,
                              current_user: Optional[User] = None) -> BytesIO:
        query = db.query(User)
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

        wb = Workbook()
        ws_summary = wb.active
        ws_summary.title = "Resumo Folha"

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
        border_style = Side(style='thin', color="000000")
        border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)

        red_font = Font(color="FF0000", bold=True)
        green_font = Font(color="008000", bold=True)
        blue_font = Font(color="0000FF", bold=True)
        weekend_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        holiday_fill = PatternFill(start_color="FFE0B2", end_color="FFE0B2", fill_type="solid")

        ws_summary.merge_cells('A1:C1')
        ws_summary['A1'].value = company_name
        ws_summary['A1'].font = Font(size=14, bold=True)
        ws_summary['A1'].alignment = Alignment(horizontal='center')

        ws_summary.merge_cells('A2:C2')
        ws_summary['A2'].value = f"CNPJ: {company_cnpj}"
        ws_summary['A2'].alignment = Alignment(horizontal='center')

        ws_summary.merge_cells('A3:C3')
        ws_summary['A3'].value = f"Relatório de Gestão - {month}/{year}"
        ws_summary['A3'].font = Font(size=12, bold=True)
        ws_summary['A3'].alignment = Alignment(horizontal='center')

        if logo_path:
            try:
                img = OpenpyxlImage(logo_path)
                img.width = 60
                img.height = 60
                ws_summary.add_image(img, 'A1')
                ws_summary.row_dimensions[1].height = 50
            except Exception:
                pass

        ws_summary.append([])

        headers_sum = ["Nome do Colaborador", "Dias Trabalhados", "Horas Trabalhadas"]
        ws_summary.append(headers_sum)
        header_row_sum = ws_summary.max_row

        for col_num, header in enumerate(headers_sum, 1):
            cell = ws_summary.cell(row=header_row_sum, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
            cell.border = border

        for user in users:
            report = report_service.get_advanced_user_report(db, user.id, month, year, current_user)
            if not report or report.summary.total_worked_minutes == 0:
                continue

            sum_data = report.summary
            ws_summary.append([
                sum_data.user_name,
                sum_data.days_worked,
                self._format_time_br(sum_data.total_worked_time)
            ])

            last_row = ws_summary.max_row
            for col in range(1, 4):
                ws_summary.cell(row=last_row, column=col).border = border

        for i, col in enumerate(ws_summary.columns, 1):
            max_length = 0
            column = get_column_letter(i)
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            ws_summary.column_dimensions[column].width = max_length + 3

        for user in users:
            report = report_service.get_advanced_user_report(db, user.id, month, year, current_user)
            if not report or report.summary.total_worked_minutes == 0:
                continue

            sheet_name = f"{user.id}-{user.name.split()[0]}"[:30]
            ws_det = wb.create_sheet(title=sheet_name)

            ws_det.merge_cells('A1:F1')
            ws_det['A1'].value = company_name
            ws_det['A1'].font = Font(size=14, bold=True)
            ws_det['A1'].alignment = Alignment(horizontal='center')

            ws_det.merge_cells('A2:F2')
            ws_det['A2'].value = f"CNPJ: {company_cnpj}"
            ws_det['A2'].alignment = Alignment(horizontal='center')

            ws_det.merge_cells('A3:F3')
            ws_det['A3'].value = f"Folha de Ponto: {user.name} - {month}/{year}"
            ws_det['A3'].font = Font(size=12, bold=True)
            ws_det['A3'].alignment = Alignment(horizontal='center')

            if logo_path:
                try:
                    img = OpenpyxlImage(logo_path)
                    img.width = 60
                    img.height = 60
                    ws_det.add_image(img, 'A1')
                    ws_det.row_dimensions[1].height = 50
                except Exception:
                    pass

            ws_det.append([])

            headers_det = ["Data", "Dia Semana", "Status", "Registros", "Trabalhado (Min)", "Trabalhado (Tempo)"]
            ws_det.append(headers_det)
            header_row_det = ws_det.max_row

            for col_num, header in enumerate(headers_det, 1):
                cell = ws_det.cell(row=header_row_det, column=col_num)
                cell.font = header_font
                cell.fill = header_fill
                cell.border = border
                cell.alignment = Alignment(horizontal='center')

            for day in report.daily_details:
                punches_str = " | ".join(day.punches)

                row_data = [
                    day.date.strftime("%d/%m/%Y"),
                    day.day_name,
                    day.status,
                    punches_str,
                    f"{day.worked_minutes} min",
                    self._format_time_br(day.worked_time)
                ]
                ws_det.append(row_data)
                last_row = ws_det.max_row

                status_cell = ws_det.cell(row=last_row, column=3)

                if "Falta" in day.status:
                    status_cell.font = red_font
                elif "Atestado" in day.status or "Abonado" in day.status:
                    status_cell.font = green_font
                elif "Feriado" in day.status:
                    status_cell.font = blue_font

                if day.is_holiday:
                    for col in range(1, 7):
                        ws_det.cell(row=last_row, column=col).fill = holiday_fill
                elif day.is_weekend:
                    for col in range(1, 7):
                        ws_det.cell(row=last_row, column=col).fill = weekend_fill

                for col in range(1, 7):
                    ws_det.cell(row=last_row, column=col).border = border

            ws_det.append([])
            ws_det.append(["TOTAIS", "", "", "",
                           f"{report.summary.total_worked_minutes} min",
                           self._format_time_br(report.summary.total_worked_time)])

            last_row = ws_det.max_row
            for col in range(1, 7):
                cell = ws_det.cell(row=last_row, column=col)
                cell.font = Font(bold=True)
                cell.border = border

            ws_det.column_dimensions['A'].width = 12
            ws_det.column_dimensions['B'].width = 15
            ws_det.column_dimensions['C'].width = 20
            ws_det.column_dimensions['D'].width = 40
            ws_det.column_dimensions['E'].width = 18
            ws_det.column_dimensions['F'].width = 20

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output


excel_service = ExcelService()
