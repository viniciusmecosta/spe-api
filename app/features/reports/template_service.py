from html import escape

from app.features.system.notification_context import base_context
from app.utils.formatters import format_short_name


class TemplateService:
    @classmethod
    def _generate_punches_html(cls, user_activity: dict[str, list[dict[str, str]]]) -> str:
        html = """
            <table class="punch-table" style="width: 100%; border-collapse: collapse; table-layout: fixed; font-family: Arial, sans-serif; font-size: 13px; color: #333; margin-bottom: 20px;">
                <thead>
                    <tr style="background-color: #f4f4f4; text-align: left; border-bottom: 2px solid #ddd;">
                        <th style="padding: 8px 6px; width: 36%;">Colaborador</th>
                        <th style="padding: 8px 6px; width: 64%;">Registros de Ponto</th>
                    </tr>
                </thead>
                <tbody>
        """
        for name, punches in user_activity.items():
            short_display = format_short_name(name)
            is_problem = len(punches) % 2 != 0
            bg_color = "#fffbf0" if is_problem else "#ffffff"

            punches_html = ""
            for p in punches:
                color = "#2E7D32" if p['type'] == 'E' else "#EF6C00"
                punches_html += f"""<span style="display: inline-block; white-space: nowrap; background-color: {color}; color: #fff; padding: 2px 7px; border-radius: 10px; font-size: 11px; font-weight: bold; margin: 2px 4px 2px 0; line-height: 1.4;">{p['type']} · {escape(p['time'])}</span>"""

            html += f"""
            <tr style="background-color: {bg_color}; border-bottom: 1px solid #eee;">
                <td style="padding: 8px 6px; vertical-align: middle; word-break: break-word; line-height: 1.3;"><strong>{escape(short_display)}</strong></td>
                <td style="padding: 6px; vertical-align: middle; line-height: 1.4;">{punches_html}</td>
            </tr>
            """

        html += "</tbody></table>"
        return html

    @classmethod
    def _generate_anomalies_html(cls, anomalies: list[str]) -> str:
        if not anomalies:
            return ""
        html = """
        <div style="margin-top: 25px;">
            <h4 style="color: #D32F2F; margin-bottom: 10px; font-size: 16px;">Anomalias Detectadas</h4>
            <ul style="background-color: #fde8e8; padding: 15px 15px 15px 30px; border-radius: 4px; color: #D32F2F; font-size: 14px; margin: 0;">
        """
        for a in anomalies:
            html += f"<li style='margin-bottom: 5px;'>{escape(a)}</li>"
        html += "</ul></div>"
        return html

    @classmethod
    def get_daily_report_html(cls, day_name: str, formatted_date: str, records_present: bool,
                              user_activity: dict[str, list[dict[str, str]]], anomalies: list[str]) -> str:
        html = f'<section style="margin-bottom:24px"><h2 style="font-size:18px;color:#18382f;margin:0 0 16px">{escape(day_name)} · {escape(formatted_date)}</h2>'

        if not records_present:
            html += "<p style='font-size: 14px; color: #666; text-align: center; padding: 20px; background: #f9f9f9; border-radius: 4px;'><em>Sem registros de ponto neste dia.</em></p>"
        else:
            html += cls._generate_punches_html(user_activity)

        html += cls._generate_anomalies_html(anomalies)

        html += "</section>"
        return html

    @staticmethod
    def get_backup_email_html(period_text: str, report_html: str, context: dict | None = None) -> str:
        info = {**base_context(), **(context or {})}
        company = escape(str(info.get('company') or info['project']))
        logo = '<img src="cid:company-logo" alt="' + company + '" width="132" style="max-width:132px;max-height:64px;width:auto;height:auto;display:block;margin-bottom:22px">' if info.get('logo_available') else ''
        metadata = ' · '.join(escape(str(info[key])) for key in ('project', 'version', 'environment'))
        address = ' · '.join(escape(str(info[key])) for key in ('cnpj', 'address', 'phone') if info.get(key))
        title = escape(str(info.get('title', 'Registros de ponto')))
        execution = escape(str(info.get('execution_id', '')))
        attempt = escape(str(info.get('attempt', 1)))
        incidents = info.get('incidents', [])
        incident_html = ''
        if incidents:
            items = ''.join('<li style="margin:6px 0;word-break:break-word;overflow-wrap:anywhere">' + escape(str(item)) + '</li>' for item in incidents)
            incident_html = '<section style="border-top:1px solid #e3e9e6;padding-top:16px"><h2 style="font-size:16px;margin:0 0 8px">Ocorrências relevantes</h2><ul style="padding-left:18px;font-size:12px;line-height:1.45;margin:0">' + items + '</ul></section>'
        return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>@media(max-width:600px){{.email-pad{{padding:16px 12px!important}}.punch-table{{font-size:12px!important}}.punch-table th,.punch-table td{{padding:6px 4px!important}}}}</style></head>
<body style="margin:0;background:#eef2ef;color:#263b33;font-family:Arial,Helvetica,sans-serif;line-height:1.5">
<div style="display:none;max-height:0;overflow:hidden">Batidas de ponto e ocorrências do período.</div>
<table role="presentation" style="width:100%;border-collapse:collapse"><tr><td align="center" style="padding:16px 6px">
<table role="presentation" style="width:100%;max-width:680px;border-collapse:collapse;background:#ffffff;border-top:4px solid #235a43">
<tr><td class="email-pad" style="padding:24px 28px 14px">{logo}
<p style="margin:0 0 6px;font-size:12px;letter-spacing:0.6px;color:#637b6d">{company}</p>
<h1 style="margin:0;font-size:22px;line-height:1.25;font-weight:600">{title}</h1>
<p style="font-size:13px;color:#617168;margin:8px 0 0">{escape(period_text)}</p></td></tr>
<tr><td class="email-pad" style="padding:8px 28px 24px">{report_html}{incident_html}</td></tr>
<tr><td class="email-pad" style="padding:18px 28px;background:#f7f9f7;border-top:1px solid #e3e9e6;color:#67766d;font-size:11px;word-break:break-word">
<strong style="color:#344b3e">{company}</strong><br>{address}<br>{metadata}<br>
Gerado em {escape(str(info['generated_at']))} · {escape(str(info['timezone']))}<br>
Tentativa {attempt}{' · Execução ' + execution if execution else ''}
</td></tr></table></td></tr></table></body></html>"""

    @staticmethod
    def get_payroll_email_html(action: str, user_name: str, month: int, year: int,
                               date_str: str) -> str:
        color = "#e65100" if action.lower() == "reabertura" else "#1565c0"
        action_title = "Folha Reaberta" if action.lower() == "reabertura" else "Folha Fechada"

        message = ('O relatório consolidado da folha de ponto segue em anexo.' if action.lower() == 'fechamento'
                   else 'As marcações foram desbloqueadas e podem receber edições ou aprovações no sistema.')
        return f"""<section style="border-left:3px solid {color};padding:4px 0 4px 20px">
<h2 style="color:{color};font-size:20px">{action_title}</h2>
<p>Competência <strong>{month:02d}/{year}</strong></p>
<p><strong>Ação:</strong> {escape(action)}<br><strong>Responsável:</strong> {escape(user_name)}<br>
<strong>Data e hora:</strong> {escape(date_str)}</p><p>{message}</p></section>"""


template_service = TemplateService()
