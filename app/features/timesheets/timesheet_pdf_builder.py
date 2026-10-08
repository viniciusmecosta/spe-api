import io
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_models import TimeRecord
from app.shared.enums import AdjustmentStatus, AdjustmentType, DayOfWeek
from app.shared.schedule_report_service import (
    format_day_groups,
    format_schedule_time_interval,
    get_schedule_transitions,
    group_schedules_by_interval,
    group_schedules_by_period,
)
from app.shared.trusted_time_service import trusted_time_service

logger = logging.getLogger(__name__)
NON_DIGIT_REGEX = re.compile(r'\D')


class TimesheetPdfBuilder:

    def _format_duration(self, total_seconds: float) -> str:
        if not isinstance(total_seconds, (int, float)):
            total_seconds = 0.0
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"

    def _format_cnpj(self, cnpj: str) -> str:
        if not cnpj:
            return "-"
        c = NON_DIGIT_REGEX.sub('', cnpj)
        if len(c) == 14:
            return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
        return cnpj

    def _format_cpf(self, cpf: str) -> str:
        if not cpf:
            return "-"
        c = NON_DIGIT_REGEX.sub('', cpf)
        if len(c) == 11:
            return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
        return cpf

    def _format_pis(self, pis: str) -> str:
        if not pis:
            return "-"
        c = NON_DIGIT_REGEX.sub('', pis)
        if len(c) == 11:
            return f"{c[:3]}.{c[3:8]}.{c[8:10]}-{c[10:]}"
        return pis

    def _format_phone(self, phone: str) -> str:
        if not phone:
            return "-"
        c = NON_DIGIT_REGEX.sub('', phone)
        if len(c) == 11:
            return f"({c[:2]}) {c[2:7]}-{c[7:]}"
        elif len(c) == 10:
            return f"({c[:2]}) {c[2:6]}-{c[6:]}"
        return phone

    def _format_daily_punches(self, daily_res, is_holiday: bool, holiday_obj) -> str:
        punch_blocks = daily_res.punch_blocks
        waiver_credit = daily_res.waiver_seconds
        formatted_waiver = self._format_duration(waiver_credit)

        if is_holiday and not punch_blocks:
            return f"Feriado: {holiday_obj.name}" if holiday_obj else "Feriado"

        punches_str = "   <font color='#94A3B8'>|</font>   ".join(punch_blocks) if punch_blocks else "-"
        if waiver_credit > 0:
            abono_str = f"Abono: {formatted_waiver}"
            return f"{punches_str}   <font color='#94A3B8'>|</font>   {abono_str}" if punches_str != "-" else abono_str
        return punches_str

    def _get_daily_adjustments(self, current_date, all_adjustments):
        day_excess = None
        abono = None
        day_extra_time_adjs = []
        for adj in (all_adjustments or []):
            if adj.target_date == current_date:
                if adj.adjustment_type == AdjustmentType.DAILY_EXCESS:
                    day_excess = adj
                elif adj.adjustment_type == AdjustmentType.WAIVER and adj.status == AdjustmentStatus.APPROVED:
                    abono = adj
                elif adj.adjustment_type == AdjustmentType.EXTRA_TIME:
                    day_extra_time_adjs.append(adj)
        return day_excess, abono, day_extra_time_adjs

    def _get_daily_schedule(self, current_date, target_day, historical_schedules):
        valid_schedules = [
            s for s in (historical_schedules or [])
            if s.valid_from <= current_date and (s.valid_until is None or s.valid_until >= current_date)
        ]
        return next((s for s in valid_schedules if s.day_of_week == target_day.value), None)

    def _is_day_absence(
        self,
        is_weekend: bool,
        is_holiday: bool,
        abono: Any,
        expected_seconds: float,
        records_count: int,
        current_date: date,
        today: date,
    ) -> bool:
        if is_weekend or is_holiday or abono is not None:
            return False
        return expected_seconds > 0 and records_count == 0 and current_date <= today

    def _resolve_day_background(
        self, is_holiday: bool, is_absence: bool, is_weekend: bool
    ) -> colors.Color | None:
        if is_holiday:
            return colors.HexColor("#FEF3C7")
        if is_absence:
            return colors.HexColor("#FEE2E2")
        if is_weekend:
            return colors.HexColor("#F1F5F9")
        return None

    def _format_absence_punches(self, punches_str: str, is_absence: bool) -> str:
        if is_absence and (not punches_str or punches_str == "-"):
            return "<font color='#991B1B'><b>Falta</b></font>"
        return punches_str

    def _build_daily_records_table(self, start_date, end_date, period_result, holidays, data_table, t_style,
                                   table_text_style, records: list[TimeRecord] | None = None,
                                   all_adjustments: list[AdjustmentRequest] | None = None,
                                   historical_schedules: list | None = None):
        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()
        current_date = start_date
        row_index = 1

        while current_date <= end_date:
            daily_res = period_result.daily_results[current_date]
            is_holiday = period_result.daily_is_holiday[current_date]
            holiday_obj = next((h for h in holidays if h.date == current_date), None)
            target_day = DayOfWeek.from_date(current_date)
            is_weekend = target_day in (DayOfWeek.SABADO, DayOfWeek.DOMINGO)

            day_records = [r for r in (records or []) if r.record_datetime.date() == current_date]
            _, abono, _ = self._get_daily_adjustments(current_date, all_adjustments)

            expected_seconds = period_result.daily_expected_seconds[current_date]

            is_absence = self._is_day_absence(
                is_weekend, is_holiday, abono, expected_seconds, len(day_records), current_date, today
            )
            bg_color = self._resolve_day_background(is_holiday, is_absence, is_weekend)
            if bg_color is not None:
                t_style.append(('BACKGROUND', (0, row_index), (-1, row_index), bg_color))

            punches_str = self._format_daily_punches(daily_res, is_holiday, holiday_obj)
            punches_str = self._format_absence_punches(punches_str, is_absence)

            accounted_res = period_result.daily_accounted_results[current_date]
            accounted_time_str = self._format_duration(accounted_res.accounted_seconds)
            unapproved_total = daily_res.unapproved_extra_seconds
            unapproved_time_str = self._format_duration(unapproved_total)

            data_table.append([
                Paragraph(current_date.strftime("%d/%m"), table_text_style),
                Paragraph(target_day.abreviado, table_text_style),
                Paragraph(punches_str, table_text_style),
                Paragraph(unapproved_time_str, table_text_style),
                Paragraph(accounted_time_str, table_text_style)
            ])

            current_date += timedelta(days=1)
            row_index += 1

        t = Table(data_table, colWidths=[45, 45, 205, 120, 120])
        t.setStyle(TableStyle(t_style))
        return t

    def _resolve_company_logo_path(self, company) -> str | None:
        if not company or not company.logo_path:
            return None
        public_path = os.path.join(settings.UPLOAD_DIR, "public", company.logo_path)
        if os.path.exists(public_path):
            return public_path
        fallback_path = os.path.join(settings.UPLOAD_DIR, company.logo_path)
        if os.path.exists(fallback_path):
            return fallback_path
        return None

    def _draw_company_header(self, story, company, title_style, section_heading_style, header_style):
        company_name = company.name if company else "Empresa Não Cadastrada"
        document_title = f"{company_name} - Registro de Ponto"
        logo_path = self._resolve_company_logo_path(company)

        if logo_path:
            try:
                logo_img = Image(logo_path, width=50, height=50)
                header_table = Table([[logo_img, Paragraph(document_title, title_style)]], colWidths=[60, 475])
                header_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT')
                ]))
                story.append(header_table)
                story.append(Spacer(1, 10))
            except (OSError, ValueError):
                story.append(Paragraph(document_title, title_style))
        else:
            story.append(Paragraph(document_title, title_style))

        company_cnpj = self._format_cnpj(company.cnpj if company else "")
        company_addr = company.address if company else "-"
        company_phone = self._format_phone(company.phone if company else "")

        story.append(Paragraph("DADOS DA EMPRESA", section_heading_style))
        company_info = [
            [Paragraph(f"<b>Razão Social:</b> {company_name}", header_style),
             Paragraph(f"<b>CNPJ:</b> {company_cnpj}", header_style)],
            [Paragraph(f"<b>Endereço:</b> {company_addr}", header_style),
             Paragraph(f"<b>Telefone:</b> {company_phone}", header_style)]
        ]
        comp_table = Table(company_info, colWidths=[320, 215])
        comp_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#F1F5F9"))
        ]))
        story.append(comp_table)
        story.append(Spacer(1, 8))

    def _draw_employee_header(self, story, user, section_heading_style, header_style):
        role_map = {
            "EMPLOYEE": "Funcionário",
            "MANAGER": "Gestor",
            "MAINTAINER": "Mantenedor"
        }
        translated_role = role_map.get(user.role, user.role)

        user_cpf_formatted = self._format_cpf(user.cpf)
        user_pis_formatted = self._format_pis(user.pis)

        story.append(Paragraph("DADOS DO COLABORADOR", section_heading_style))
        employee_info = [
            [Paragraph(f"<b>Colaborador:</b> {user.name}", header_style),
             Paragraph(f"<b>CPF:</b> {user_cpf_formatted}", header_style)],
            [Paragraph(f"<b>PIS:</b> {user_pis_formatted}", header_style),
             Paragraph(f"<b>Cargo:</b> {translated_role}", header_style)]
        ]
        emp_table = Table(employee_info, colWidths=[320, 215])
        emp_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#F1F5F9"))
        ]))
        story.append(emp_table)
        story.append(Spacer(1, 8))

    def _format_day_groups(self, days: list[int]) -> str:
        return format_day_groups(days)

    def _get_schedule_transitions(self, user, start_date, end_date):
        return get_schedule_transitions(user, start_date, end_date)

    def _group_schedules_by_period(self, user, transitions):
        return group_schedules_by_period(user, transitions)

    def _format_schedule_time_interval(self, sch) -> str | None:
        return format_schedule_time_interval(sch)

    def _group_schedules_by_interval(self, schedules) -> dict[str, list[int]]:
        return group_schedules_by_interval(schedules)

    def _build_schedule_table_element(self, grouped: dict[str, list[int]], header_style) -> Table:
        if not grouped:
            no_sch_data = [[Paragraph("Sem expediente cadastrado", header_style)]]
            no_sch_table = Table(no_sch_data, colWidths=[535])
            no_sch_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ]))
            return no_sch_table

        rows = []
        for time_str, days in grouped.items():
            day_str = self._format_day_groups(days)
            rows.append([
                Paragraph(f"<b>{day_str}:</b>", header_style),
                Paragraph(time_str, header_style)
            ])

        sch_table = Table(rows, colWidths=[180, 355])
        sch_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#F1F5F9"))
        ]))
        return sch_table

    def _build_work_schedules_section(self, story, user, start_date, end_date, section_heading_style, header_style):
        if not user or not user.historical_schedules:
            return
        transitions = self._get_schedule_transitions(user, start_date, end_date)
        periods = self._group_schedules_by_period(user, transitions)
        if not periods:
            return

        story.append(Paragraph("EXPEDIENTE CADASTRADO", section_heading_style))

        is_single_period = len(periods) == 1 and periods[0][0] == start_date and periods[0][1] == end_date

        for p_start, p_end, schedules in periods:
            if not is_single_period:
                period_str = f"<b>Período:</b> {p_start.strftime('%d/%m/%Y')} a {p_end.strftime('%d/%m/%Y')}"
                story.append(Paragraph(period_str, header_style))
                story.append(Spacer(1, 2))

            grouped = self._group_schedules_by_interval(schedules)
            table = self._build_schedule_table_element(grouped, header_style)
            story.append(table)
            story.append(Spacer(1, 5))

    def _calculate_summary_totals(self, period_result) -> tuple[str, str, str]:
        total_gross = getattr(period_result, "total_gross_worked_seconds", None)
        if not isinstance(total_gross, (int, float)):
            net_sec = getattr(period_result, "total_net_worked_seconds", 0.0)
            unapp_sec = getattr(period_result, "total_unapproved_extra_seconds", 0.0)
            net_val = net_sec if isinstance(net_sec, (int, float)) else 0.0
            unapp_val = unapp_sec if isinstance(unapp_sec, (int, float)) else 0.0
            total_gross = net_val + unapp_val

        total_unapproved = getattr(period_result, "total_unapproved_extra_seconds", 0.0)
        unapproved_val = total_unapproved if isinstance(total_unapproved, (int, float)) else 0.0

        total_accounted = getattr(period_result, "total_accounted_seconds", 0.0)
        accounted_val = total_accounted if isinstance(total_accounted, (int, float)) else 0.0

        return (
            self._format_duration(total_gross),
            self._format_duration(unapproved_val),
            self._format_duration(accounted_val),
        )

    def _build_summary_table(
        self, total_duration_str: str, total_unapproved_str: str, total_accounted_str: str, header_style
    ) -> Table:
        summary_info = [
            [
                Paragraph(
                    "<b>Total de Horas Trabalhadas:</b>",
                    ParagraphStyle(
                        "BoldHeaderStyle",
                        fontSize=9,
                        leading=12,
                        fontName="Helvetica-Bold",
                        textColor=colors.HexColor("#000000"),
                    ),
                ),
                Paragraph(total_duration_str, header_style),
            ],
            [
                Paragraph(
                    "<b>Horas Não Autorizadas:</b>",
                    ParagraphStyle(
                        "BoldHeaderStyle",
                        fontSize=9,
                        leading=12,
                        fontName="Helvetica-Bold",
                        textColor=colors.HexColor("#000000"),
                    ),
                ),
                Paragraph(total_unapproved_str, header_style),
            ],
            [
                Paragraph(
                    "<b>Total de Horas Contabilizadas:</b>",
                    ParagraphStyle(
                        "BoldHeaderStyle",
                        fontSize=9,
                        leading=12,
                        fontName="Helvetica-Bold",
                        textColor=colors.HexColor("#000000"),
                    ),
                ),
                Paragraph(total_accounted_str, header_style),
            ],
        ]
        sum_table = Table(summary_info, colWidths=[175, 360])
        sum_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return sum_table

    def build(
        self,
        user,
        company,
        month: int,
        year: int,
        start_date: date,
        end_date: date,
        today: date,
        records: list[TimeRecord],
        holidays,
        all_adjustments,
        historical_schedules,
        period_result,
    ):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=15,
            bottomMargin=15,
            title="Espelho de Ponto Oficial",
            author=settings.PROJECT_NAME,
            subject="Relatório Oficial de Ponto",
            creator=settings.PROJECT_NAME,
        )
        story = []

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=14,
            leading=17,
            alignment=1,
            spaceAfter=10,
        )

        section_heading_style = ParagraphStyle(
            "SectionHeading",
            fontSize=9,
            leading=12,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1A365D"),
            spaceAfter=2,
        )

        header_style = ParagraphStyle(
            "HeaderStyle",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#222222"),
        )

        table_text_style = ParagraphStyle(
            "TableText",
            fontSize=9,
            leading=12,
            alignment=1,
        )

        table_header_style = ParagraphStyle(
            "TableHeader",
            fontSize=10,
            leading=13,
            fontName="Helvetica-Bold",
            alignment=1,
            textColor=colors.white,
        )

        self._draw_company_header(story, company, title_style, section_heading_style, header_style)
        self._draw_employee_header(story, user, section_heading_style, header_style)

        period_info = [
            [
                Paragraph(f"<b>Mês/Ano de Referência:</b> {month:02d}/{year}", header_style),
                Paragraph(f"<b>Data de Emissão:</b> {today.strftime('%d/%m/%Y')}", header_style),
            ]
        ]
        per_table = Table(period_info, colWidths=[320, 215])
        per_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(per_table)
        story.append(Spacer(1, 8))

        data_table = [
            [
                Paragraph("Data", table_header_style),
                Paragraph("Dia", table_header_style),
                Paragraph("Registros de Ponto", table_header_style),
                Paragraph("Horas Não Autorizadas", table_header_style),
                Paragraph("Horas Contabilizadas", table_header_style),
            ]
        ]

        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A365D")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]


        story.append(
            self._build_daily_records_table(
                start_date=start_date,
                end_date=end_date,
                period_result=period_result,
                holidays=holidays,
                data_table=data_table,
                t_style=t_style,
                table_text_style=table_text_style,
                records=records,
                all_adjustments=all_adjustments,
                historical_schedules=historical_schedules,
            )
        )
        story.append(Spacer(1, 10))

        total_dur, total_unapp, total_acc = self._calculate_summary_totals(period_result)
        sum_table = self._build_summary_table(total_dur, total_unapp, total_acc, header_style)
        story.append(sum_table)
        story.append(Spacer(1, 8))

        self._build_work_schedules_section(story, user, start_date, end_date, section_heading_style, header_style)

        note_style = ParagraphStyle(
            'NoteStyle',
            fontSize=8,
            leading=10,
            fontName='Helvetica-Oblique',
            textColor=colors.HexColor("#64748B")
        )
        now, _ = trusted_time_service.get_trusted_time()
        generated_at = now.strftime("%d/%m/%Y %H:%M")
        story.append(Paragraph("* Nota: O formato de tempo exibido é HH:MM (Horas:Minutos).", note_style))
        story.append(
            Paragraph("  Exemplo: 10:20 representa exatamente 10 horas e 20 minutos contabilizados.", note_style))
        story.append(Paragraph(f"* Documento gerado em: {generated_at}", note_style))
        story.append(Spacer(1, 8))

        term_style = ParagraphStyle(
            'TermStyle',
            fontSize=8,
            leading=11,
            alignment=4,
            textColor=colors.HexColor("#444444")
        )
        story.append(Paragraph(
            "Reconheço a exatidão das anotações de horários registradas neste documento, servindo o mesmo como espelho de ponto mensal regulamentar. Declaro estar ciente de que as informações contidas refletem fielmente as jornadas executadas, passível de validação manual ou assinatura eletrônica via Gov.br.",
            term_style))
        story.append(Spacer(1, 30))

        sig_text_style = ParagraphStyle(
            'SigText',
            fontSize=8,
            leading=11,
            alignment=1,
            textColor=colors.HexColor("#555555")
        )
        sig_line = [
            [Paragraph("_______________________________________<br/>Assinatura do Colaborador",
                       sig_text_style),
             Paragraph("_______________________________________<br/>Representante da Empresa", sig_text_style)]
        ]
        sig_table = Table(sig_line, colWidths=[265, 270])
        story.append(sig_table)

        company_name = company.name if company else "Empresa Não Cadastrada"

        def _add_pdf_meta(canvas, document):
            canvas.setTitle(f"{company_name} - Registro de Ponto")
            canvas.setAuthor(company_name)

        doc.build(story, onFirstPage=_add_pdf_meta, onLaterPages=_add_pdf_meta)
        buffer.seek(0)
        return buffer
