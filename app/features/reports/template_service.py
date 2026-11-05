from html import escape

from app.features.system.notification_context import (
    base_context,
    company_identity,
    format_company_phone,
)


class TemplateService:
    @classmethod
    def _generate_punches_html(cls, user_activity: dict[str, list[dict[str, str]]]) -> str:
        html = """
            <table class="punch-table" style="width: 100%; border-collapse: collapse; table-layout: fixed; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; font-size: 13px; color: #1f2937; margin-bottom: 18px; border: 1px solid #e5e7eb;">
                <thead>
                    <tr style="background-color: #f8fafc; text-align: left; border-bottom: 1px solid #d1d5db;">
                        <th style="padding: 9px 10px; width: 38%; font-weight: 600; color: #374151;">Colaborador</th>
                        <th style="padding: 9px 10px; width: 62%; font-weight: 600; color: #374151;">Registros de Ponto</th>
                    </tr>
                </thead>
                <tbody>
        """
        for name, punches in user_activity.items():
            is_problem = len(punches) % 2 != 0
            bg_color = "#fffbf0" if is_problem else "#ffffff"

            punches_html = ""
            for p in punches:
                color = "#2E7D32" if p['type'] == 'E' else "#EF6C00"
                punches_html += f"""<span style="display: inline-block; white-space: nowrap; background-color: {color}; color: #ffffff; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; margin: 2px 4px 2px 0; line-height: 1.35;">{p['type']} {escape(p['time'])}</span>"""

            html += f"""
            <tr style="background-color: {bg_color}; border-bottom: 1px solid #e5e7eb;">
                <td style="padding: 8px 10px; vertical-align: middle; word-break: break-word; line-height: 1.35; color: #111827;"><strong>{escape(name)}</strong></td>
                <td style="padding: 7px 10px; vertical-align: middle; line-height: 1.4;">{punches_html}</td>
            </tr>
            """

        html += "</tbody></table>"
        return html

    @classmethod
    def _generate_anomalies_html(cls, anomalies: list[str]) -> str:
        if not anomalies:
            return ""
        html = """
        <div style="margin-top: 16px; border: 1px solid #f3d2d2; background-color: #fcf4f4; padding: 12px 14px;">
            <p style="color: #991b1b; margin: 0 0 8px; font-size: 13px; font-weight: 600;">Anomalias Detectadas</p>
            <ul style="padding: 0 0 0 18px; color: #7f1d1d; font-size: 13px; margin: 0;">
        """
        for a in anomalies:
            html += f"<li style='margin-bottom: 4px;'>{escape(a)}</li>"
        html += "</ul></div>"
        return html

    @classmethod
    def get_daily_report_html(cls, day_name: str, formatted_date: str, records_present: bool,
                              user_activity: dict[str, list[dict[str, str]]], anomalies: list[str]) -> str:
        html = f'<section style="margin-bottom:22px"><h2 style="font-size:15px;font-weight:600;color:#111827;margin:0 0 10px;padding-bottom:6px;border-bottom:1px solid #e5e7eb">{escape(day_name)} — {escape(formatted_date)}</h2>'

        if not records_present:
            html += "<p style='font-size: 13px; color: #4b5563; padding: 12px 14px; background: #f8fafc; border: 1px solid #e5e7eb; margin: 0;'>Sem registros de ponto neste dia.</p>"
        else:
            html += cls._generate_punches_html(user_activity)

        html += cls._generate_anomalies_html(anomalies)

        html += "</section>"
        return html

    @staticmethod
    def get_backup_email_html(period_text: str, report_html: str, context: dict | None = None) -> str:
        info = {**base_context(), **(context or {})}
        company = escape(str(info.get('company') or info['project']))
        logo = '<img src="cid:company-logo" alt="' + company + '" width="120" style="max-width:120px;max-height:52px;width:auto;height:auto;display:block;margin-bottom:14px">' if info.get('logo_available') else ''
        metadata = ' · '.join(escape(str(info[key])) for key in ('project', 'version', 'environment'))
        _, cnpj = company_identity(info)
        phone = format_company_phone(str(info.get('phone') or ''))
        address = ' · '.join(escape(str(value)) for value in (cnpj, info.get('address'), phone) if value)
        title = escape(str(info.get('title', 'Registros de ponto')))
        execution = escape(str(info.get('execution_id', '')))
        attempt = escape(str(info.get('attempt', 1)))
        incidents = info.get('incidents', [])
        incident_html = ''
        if incidents:
            items = ''.join('<li style="margin:5px 0;word-break:break-word;overflow-wrap:anywhere">' + escape(str(item)) + '</li>' for item in incidents)
            incident_html = '<section style="border-top:1px solid #e5e7eb;padding-top:14px;margin-top:8px"><h2 style="font-size:14px;font-weight:600;color:#111827;margin:0 0 6px">Ocorrências relevantes</h2><ul style="padding-left:18px;font-size:12px;color:#374151;line-height:1.45;margin:0">' + items + '</ul></section>'
        return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>@media(max-width:600px){{.email-pad{{padding:16px 12px!important}}.punch-table{{font-size:12px!important}}.punch-table th,.punch-table td{{padding:6px 4px!important}}}}</style></head>
<body style="margin:0;background:#f3f4f6;color:#1f2937;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;line-height:1.5">
<div style="display:none;max-height:0;overflow:hidden">Batidas de ponto e ocorrências do período.</div>
<table role="presentation" style="width:100%;border-collapse:collapse"><tr><td align="center" style="padding:20px 8px">
<table role="presentation" style="width:100%;max-width:680px;border-collapse:collapse;background:#ffffff;border:1px solid #d1d5db">
<tr><td class="email-pad" style="padding:22px 26px 16px;border-bottom:1px solid #e5e7eb">{logo}
<p style="margin:0 0 4px;font-size:12px;font-weight:600;color:#4b5563">{company}</p>
<h1 style="margin:0;font-size:20px;line-height:1.3;font-weight:600;color:#111827">{title}</h1>
<p style="font-size:13px;color:#4b5563;margin:6px 0 0">{escape(period_text)}</p></td></tr>
<tr><td class="email-pad" style="padding:18px 26px 22px">{report_html}{incident_html}</td></tr>
<tr><td class="email-pad" style="padding:16px 26px;background:#f9fafb;border-top:1px solid #e5e7eb;color:#4b5563;font-size:11px;line-height:1.55;word-break:break-word">
<strong style="color:#111827">{company}</strong><br>{address}<br>{metadata}<br>
Gerado em {escape(str(info['generated_at']))} ({escape(str(info['timezone']))})<br>
Tentativa {attempt}{' · Execução ' + execution if execution else ''}
</td></tr></table></td></tr></table></body></html>"""

    @staticmethod
    def get_payroll_email_html(action: str, user_name: str, month: int, year: int,
                               date_str: str) -> str:
        color = "#e65100" if action.lower() == "reabertura" else "#1565c0"
        action_title = "Folha Reaberta" if action.lower() == "reabertura" else "Folha Fechada"

        message = ('O relatório consolidado da folha de ponto segue em anexo.' if action.lower() == 'fechamento'
                   else 'As marcações foram desbloqueadas e podem receber edições ou aprovações no sistema.')
        return f"""<section style="border:1px solid #e5e7eb;padding:16px 18px;background:#ffffff">
<h2 style="color:{color};font-size:18px;margin:0 0 10px;font-weight:600">{action_title}</h2>
<p style="margin:0 0 10px;font-size:13px;color:#1f2937">Competência <strong>{month:02d}/{year}</strong></p>
<p style="margin:0 0 10px;font-size:13px;color:#374151;line-height:1.55"><strong>Ação:</strong> {escape(action)}<br><strong>Responsável:</strong> {escape(user_name)}<br>
<strong>Data e hora:</strong> {escape(date_str)}</p><p style="margin:0;font-size:13px;color:#4b5563">{message}</p></section>"""


template_service = TemplateService()
