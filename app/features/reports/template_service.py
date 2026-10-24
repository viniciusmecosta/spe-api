from html import escape

from app.features.system.notification_context import base_context


class TemplateService:
    @classmethod
    def _generate_punches_html(cls, user_activity: dict[str, list[dict[str, str]]]) -> str:
        html = """
            <table class="punch-table" style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px; color: #333; margin-bottom: 25px;">
                <thead>
                    <tr style="background-color: #f4f4f4; text-align: left; border-bottom: 2px solid #ddd;">
                        <th style="padding: 12px 8px; width: 40%;">Colaborador</th>
                        <th style="padding: 12px 8px;">Registros de Ponto</th>
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
                punches_html += f"""<span style="display: inline-block; background-color: {color}; color: #fff; padding: 4px 10px; border-radius: 14px; font-size: 13px; font-weight: bold; margin-right: 6px; margin-bottom: 4px;">{p['type']} · {escape(p['time'])}</span>"""

            html += f"""
            <tr style="background-color: {bg_color}; border-bottom: 1px solid #eee;">
                <td style="padding: 10px 8px;"><strong>{escape(name)}</strong></td>
                <td style="padding: 10px 8px;">{punches_html}</td>
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
        execution = escape(str(info.get('execution_id', '')))
        attempt = escape(str(info.get('attempt', 1)))
        incidents = info.get('incidents', [])
        incident_html = ''
        if incidents:
            items = ''.join('<li style="margin:8px 0">' + escape(str(item)) + '</li>' for item in incidents)
            incident_html = '<section style="border-top:1px solid #e3e9e6;padding-top:20px"><h2 style="font-size:18px">Ocorrências relevantes</h2><ul style="padding-left:20px;font-size:14px">' + items + '</ul></section>'
        return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>@media(max-width:600px){{.email-pad{{padding:24px 16px!important}}.punch-table td{{display:block!important;width:auto!important;padding:8px 0!important}}}}</style></head>
<body style="margin:0;background:#eef2ef;color:#263b33;font-family:Arial,Helvetica,sans-serif;line-height:1.6">
<div style="display:none;max-height:0;overflow:hidden">Batidas de ponto e ocorrências do período.</div>
<table role="presentation" style="width:100%;border-collapse:collapse"><tr><td align="center" style="padding:24px 8px">
<table role="presentation" style="width:100%;max-width:680px;border-collapse:collapse;background:#ffffff;border-top:4px solid #235a43">
<tr><td class="email-pad" style="padding:32px 36px 20px">{logo}
<p style="margin:0 0 8px;font-size:12px;letter-spacing:1px;color:#637b6d">{company}</p>
<h1 style="margin:0;font-size:26px;line-height:1.25;font-weight:600">Registros de ponto</h1>
<p style="font-size:14px;color:#617168;margin:12px 0 0">{escape(period_text)}</p></td></tr>
<tr><td class="email-pad" style="padding:12px 36px 32px">{report_html}{incident_html}</td></tr>
<tr><td class="email-pad" style="padding:24px 36px;background:#f7f9f7;border-top:1px solid #e3e9e6;color:#67766d;font-size:12px">
<strong style="color:#344b3e">{company}</strong><br>{address}<br>{metadata}<br>
Gerado em {escape(str(info['generated_at']))} · {escape(str(info['timezone']))}<br>
Tentativa {attempt}{' · Execução ' + execution if execution else ''}
</td></tr></table></td></tr></table></body></html>"""

    @staticmethod
    def get_payroll_email_html(action: str, user_name: str, month: int, year: int,
                               date_str: str) -> str:
        color = "#e65100" if action.lower() == "reabertura" else "#1565c0"
        action_title = "Folha Reaberta" if action.lower() == "reabertura" else "Folha Fechada"

        return f"""
        <html>
        <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; background-color: #f9f9f9;">
            <div style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: {color}; color: #ffffff; padding: 20px; text-align: center;">
                    <h2 style="margin: 0; font-size: 24px; font-weight: 500;">{action_title}</h2>
                </div>
                <div style="padding: 30px;">
                    <p style="font-size: 16px; margin-top: 0;">Olá,</p>
                    <p style="font-size: 16px;">O status da folha de ponto referente a <strong>{month:02d}/{year}</strong> foi alterado.</p>
                    
                    <div style="background-color: #f4f6f8; border-left: 4px solid {color}; padding: 15px; margin: 20px 0; border-radius: 0 4px 4px 0;">
                        <table style="width: 100%; border: none; font-size: 15px;">
                            <tr>
                                <td style="padding: 5px 0; color: #555; width: 120px;"><strong>Ação:</strong></td>
                                <td style="padding: 5px 0; font-weight: bold; color: {color};">{escape(action)}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0; color: #555;"><strong>Responsável:</strong></td>
                                <td style="padding: 5px 0;">{escape(user_name)}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0; color: #555;"><strong>Data e Hora:</strong></td>
                                <td style="padding: 5px 0;">{date_str}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <p style="font-size: 15px; color: #666; margin-bottom: 0;">{'O relatório consolidado e auditável da folha de ponto segue em anexo para seus registros.' if action.lower() == 'fechamento' else 'As marcações de ponto para este período foram desbloqueadas e já podem receber edições ou aprovações no sistema.'}</p>
                </div>
                <div style="background-color: #f1f1f1; padding: 20px 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                    <p style="font-size: 14px; color: #777; margin: 0;">Atenciosamente,</p>
                    <p style="font-size: 15px; font-weight: bold; color: #555; margin: 5px 0 0 0;">SPE - Sistema de Ponto Eletrônico</p>
                </div>
            </div>
        </body>
        </html>
        """


template_service = TemplateService()
