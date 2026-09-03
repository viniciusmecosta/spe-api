import io
import logging
import os
import re
import zipfile
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.companies.company_repository import (
    async_company_repository,
    company_repository,
)
from app.features.holidays.holiday_repository import (
    async_holiday_repository,
    holiday_repository,
)
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_repository import (
    async_time_record_repository,
    time_record_repository,
)
from app.features.timesheets.timesheet_exceptions import (
    FutureTimesheetNotAllowedError,
    NoTimesheetRecordsFoundError,
    TimesheetUserNotFoundError,
)
from app.features.users.user_models import User
from app.features.users.user_repository import (
    async_user_repository,
    user_repository,
)
from app.shared import deps
from app.shared.enums import AdjustmentStatus, AdjustmentType, DayOfWeek, UserRole
from app.shared.time_calculation_service import time_calculation_service
from app.shared.trusted_time_service import trusted_time_service

logger = logging.getLogger(__name__)

NON_DIGIT_REGEX = re.compile(r'\D')


class TimesheetService:
    def __init__(self, db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None):
        self.db = db

    def validate_date_not_future(self, month: int, year: int) -> None:
        now = datetime.now()
        if year > now.year or (year == now.year and month > now.month):
            raise FutureTimesheetNotAllowedError()

    def _format_duration(self, total_seconds: float) -> str:
        total_minutes = int(round(total_seconds / 60))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"

    def _format_cnpj(self, cnpj: str) -> str:
        if not cnpj: return "-"
        c = NON_DIGIT_REGEX.sub('', cnpj)
        if len(c) == 14:
            return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
        return cnpj

    def _format_cpf(self, cpf: str) -> str:
        if not cpf: return "-"
        c = NON_DIGIT_REGEX.sub('', cpf)
        if len(c) == 11:
            return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
        return cpf

    def _format_pis(self, pis: str) -> str:
        if not pis: return "-"
        c = NON_DIGIT_REGEX.sub('', pis)
        if len(c) == 11:
            return f"{c[:3]}.{c[3:8]}.{c[8:10]}-{c[10:]}"
        return pis

    def _format_phone(self, phone: str) -> str:
        if not phone: return "-"
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

    def _build_daily_records_table(self, start_date, end_date, period_result, holidays, data_table, t_style,
                                   table_text_style, records: list[TimeRecord] | None = None,
                                   all_adjustments: list[AdjustmentRequest] | None = None,
                                   historical_schedules: list | None = None):
        current_date = start_date
        row_index = 1

        while current_date <= end_date:
            daily_res = period_result.daily_results[current_date]
            is_holiday = period_result.daily_is_holiday[current_date]
            holiday_obj = next((h for h in holidays if h.date == current_date), None)
            target_day = DayOfWeek.from_date(current_date)
            is_weekend = target_day in (DayOfWeek.SABADO, DayOfWeek.DOMINGO)

            if is_weekend:
                t_style.append(('BACKGROUND', (0, row_index), (-1, row_index), colors.HexColor("#F1F5F9")))

            punches_str = self._format_daily_punches(daily_res, is_holiday, holiday_obj)

            day_records = [r for r in (records or []) if r.record_datetime.date() == current_date]
            valid_schedules = [
                s for s in (historical_schedules or [])
                if s.valid_from <= current_date and (s.valid_until is None or s.valid_until >= current_date)
            ]
            day_schedule = next((s for s in valid_schedules if s.day_of_week == target_day.value), None)
            day_excess = next((adj for adj in (all_adjustments or []) if
                               adj.target_date == current_date and
                               adj.adjustment_type == AdjustmentType.DAILY_EXCESS), None)

            abono = next((adj for adj in (all_adjustments or []) if
                          adj.target_date == current_date and
                          adj.adjustment_type == AdjustmentType.WAIVER and
                          adj.status == AdjustmentStatus.APPROVED), None)
            day_unapproved_extras = [adj for adj in (all_adjustments or []) if
                                     adj.target_date == current_date and
                                     adj.adjustment_type == AdjustmentType.EXTRA_TIME and
                                     adj.status in [AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED]]

            accounted_res = time_calculation_service.calculate_accounted_time(
                day_records=day_records,
                schedule=day_schedule,
                daily_excess_adj=day_excess,
                waiver_adj=abono,
                unapproved_extra_adjs=day_unapproved_extras,
            )
            accounted_time_str = self._format_duration(accounted_res.accounted_seconds)
            unapproved_time_str = self._format_duration(daily_res.unapproved_extra_seconds)

            data_table.append([
                Paragraph(current_date.strftime("%d/%m/%Y"), table_text_style),
                Paragraph(target_day.abreviado, table_text_style),
                Paragraph(punches_str, table_text_style),
                Paragraph(unapproved_time_str, table_text_style),
                Paragraph(accounted_time_str, table_text_style)
            ])

            current_date += timedelta(days=1)
            row_index += 1

        t = Table(data_table, colWidths=[65, 65, 215, 95, 95])
        t.setStyle(TableStyle(t_style))
        return t

    def _draw_company_header(self, story, company, title_style, section_heading_style, header_style):
        company_name = company.name if company else "Empresa Não Cadastrada"
        document_title = f"{company_name} - Registro de Ponto"

        if company and company.logo_path:
            full_logo_path = os.path.join(settings.UPLOAD_DIR, company.logo_path)
            if os.path.exists(full_logo_path):
                try:
                    logo_img = Image(full_logo_path, width=50, height=50)
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
        if not days:
            return ""
        days = sorted(set(days))

        blocks = []
        current_block = [days[0]]
        for d in days[1:]:
            if d == current_block[-1] + 1:
                current_block.append(d)
            else:
                blocks.append(current_block)
                current_block = [d]
        blocks.append(current_block)

        parts = []
        for block in blocks:
            if len(block) >= 3:
                parts.append(f"{DayOfWeek(block[0]).abreviado} a {DayOfWeek(block[-1]).abreviado}")
            elif len(block) == 2:
                parts.append(f"{DayOfWeek(block[0]).abreviado} e {DayOfWeek(block[1]).abreviado}")
            else:
                parts.append(DayOfWeek(block[0]).abreviado)

        if len(parts) > 1:
            return ", ".join(parts[:-1]) + " e " + parts[-1]
        return parts[0]

    def _get_schedule_transitions(self, user, start_date, end_date):
        transitions = {start_date, end_date + timedelta(days=1)}
        for sch in user.historical_schedules:
            if sch.valid_from and start_date <= sch.valid_from <= end_date:
                transitions.add(sch.valid_from)
            if sch.valid_until and start_date <= sch.valid_until <= end_date:
                transitions.add(sch.valid_until + timedelta(days=1))
        return sorted(transitions)

    def _group_schedules_by_period(self, user, transitions):
        periods = []
        for i in range(len(transitions) - 1):
            p_start = transitions[i]
            p_end = transitions[i + 1] - timedelta(days=1)
            if p_start > p_end:
                continue
            active_schedules = []
            for sch in user.historical_schedules:
                if sch.valid_from <= p_end and (not sch.valid_until or sch.valid_until >= p_start):
                    active_schedules.append(sch)
            periods.append((p_start, p_end, active_schedules))
        return periods

    def _format_schedule_time_interval(self, sch) -> str | None:
        if not sch.entry_1 and not sch.entry_2 and not sch.exit_1 and not sch.exit_2:
            return None
        parts = []
        if sch.entry_1 and sch.exit_1:
            parts.append(f"{sch.entry_1.strftime('%H:%M')} às {sch.exit_1.strftime('%H:%M')}")
        if sch.entry_2 and sch.exit_2:
            parts.append(f"{sch.entry_2.strftime('%H:%M')} às {sch.exit_2.strftime('%H:%M')}")
        return " e ".join(parts) if parts else None

    def _group_schedules_by_interval(self, schedules) -> dict[str, list[int]]:
        grouped = {}
        for sch in schedules:
            time_str = self._format_schedule_time_interval(sch)
            if time_str:
                grouped.setdefault(time_str, []).append(sch.day_of_week)
        return grouped

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

    async def generate_user_timesheet_pdf(self, db: Any | None = None, user_id: int = 0, month: int = 0,
                                          year: int = 0) -> io.BytesIO:
        session = db if db is not None else self.db
        assert session is not None
        if hasattr(session, "sync_session"):
            user = await async_user_repository.get(session, user_id)
        else:
            user = user_repository.get(session, user_id)
        if not user:
            raise TimesheetUserNotFoundError(user_id=user_id)

        tz = ZoneInfo(settings.TIMEZONE)
        today = datetime.now(tz).date()

        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        if hasattr(session, "sync_session"):
            records = await async_time_record_repository.get_by_range(session, user_id, start_dt, end_dt)
            holidays = await async_holiday_repository.get_by_month(session, month, year)
            adj_stmt = select(AdjustmentRequest).where(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None)
            )
            adj_res = await session.scalars(adj_stmt)
            all_adjustments = list(adj_res.all())
            company = await async_company_repository.get_current(session)
        else:
            records = time_record_repository.get_by_range(session, user_id, start_dt, end_dt)
            holidays = holiday_repository.get_by_month(session, month, year)
            all_adjustments = session.query(AdjustmentRequest).filter(
                AdjustmentRequest.user_id == user_id,
                AdjustmentRequest.target_date >= start_date,
                AdjustmentRequest.target_date <= end_date,
                AdjustmentRequest.deleted_at.is_(None)
            ).all()
            company = company_repository.get_current(session)

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
            creator=settings.PROJECT_NAME
        )
        story = []

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=14,
            leading=17,
            alignment=1,
            spaceAfter=10
        )

        section_heading_style = ParagraphStyle(
            'SectionHeading',
            fontSize=9,
            leading=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor("#1A365D"),
            spaceAfter=2
        )

        header_style = ParagraphStyle(
            'HeaderStyle',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#222222")
        )

        table_text_style = ParagraphStyle(
            'TableText',
            fontSize=9,
            leading=12,
            alignment=1
        )

        table_header_style = ParagraphStyle(
            'TableHeader',
            fontSize=10,
            leading=13,
            fontName='Helvetica-Bold',
            alignment=1,
            textColor=colors.white
        )

        self._draw_company_header(story, company, title_style, section_heading_style, header_style)
        self._draw_employee_header(story, user, section_heading_style, header_style)

        period_info = [
            [Paragraph(f"<b>Mês/Ano de Referência:</b> {month:02d}/{year}", header_style),
             Paragraph(f"<b>Data de Emissão:</b> {today.strftime('%d/%m/%Y')}", header_style)]
        ]
        per_table = Table(period_info, colWidths=[320, 215])
        per_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(per_table)
        story.append(Spacer(1, 8))

        data_table = [[
            Paragraph("Data", table_header_style),
            Paragraph("Dia", table_header_style),
            Paragraph("Registros de Ponto", table_header_style),
            Paragraph("Tempo Ñ Aut...", table_header_style),
            Paragraph("Tempo Contabilizado", table_header_style)
        ]]

        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1A365D")),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]

        period_result = time_calculation_service.calculate_period_time(
            start_date=start_date,
            end_date=end_date,
            records=records,
            adjustments=all_adjustments,
            holidays=holidays,
            historical_schedules=user.historical_schedules if user else []
        )

        story.append(self._build_daily_records_table(
            start_date=start_date,
            end_date=end_date,
            period_result=period_result,
            holidays=holidays,
            data_table=data_table,
            t_style=t_style,
            table_text_style=table_text_style,
            records=records,
            all_adjustments=all_adjustments,
            historical_schedules=user.historical_schedules if user else []
        ))
        story.append(Spacer(1, 10))

        total_duration_str = self._format_duration(period_result.total_net_worked_seconds)
        summary_info = [
            [Paragraph("<b>Total de Horas Trabalhadas:</b>",
                       ParagraphStyle('BoldHeaderStyle', fontSize=9, leading=12, fontName='Helvetica-Bold',
                                      textColor=colors.HexColor("#000000"))),
             Paragraph(total_duration_str, header_style)]
        ]
        sum_table = Table(summary_info, colWidths=[175, 360])
        sum_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
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

    async def generate_all_timesheets_pdf_zip(self, db: Any | None = None, month: int = 0, year: int = 0,
                                        employee_ids: list[int] | None = None) -> io.BytesIO:
        session = db if db is not None else self.db
        assert session is not None
        tz = ZoneInfo(settings.TIMEZONE)
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)

        if hasattr(session, "sync_session"):
            stmt = (
                select(User)
                .join(TimeRecord, User.id == TimeRecord.user_id)
                .where(
                    User.role == UserRole.EMPLOYEE,
                    User.is_exempt_from_rules.is_(False),
                    TimeRecord.record_datetime >= start_dt,
                    TimeRecord.record_datetime <= end_dt,
                    TimeRecord.is_ignored.is_(False),
                )
                .distinct()
            )
            if employee_ids:
                stmt = stmt.where(User.id.in_(employee_ids))
            res = await session.scalars(stmt)
            users = list(res.all())
        else:
            query = session.query(User).join(TimeRecord, User.id == TimeRecord.user_id).filter(
                User.role == UserRole.EMPLOYEE,
                User.is_exempt_from_rules.is_(False),
                TimeRecord.record_datetime >= start_dt,
                TimeRecord.record_datetime <= end_dt,
                TimeRecord.is_ignored == False
            ).distinct()
            if employee_ids:
                query = query.filter(User.id.in_(employee_ids))
            users = query.all()

        if not users:
            raise NoTimesheetRecordsFoundError()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for user in users:
                try:
                    pdf_buffer = await self.generate_user_timesheet_pdf(session, user.id, month, year)
                    safe_name = "".join([c for c in user.name if c.isalpha() or c.isdigit() or c == ' ']).rstrip()
                    safe_name = safe_name.replace(" ", "_")

                    filename = f"espelho_ponto_{safe_name}_{month:02d}_{year}.pdf"
                    zip_file.writestr(filename, pdf_buffer.getvalue())
                except (ValueError, OSError, RuntimeError):
                    logger.exception(f"Erro ao gerar espelho de ponto em lote (User {user.id})")
                    continue

        zip_buffer.seek(0)
        return zip_buffer
