from typing import Dict, List


class TemplateService:
    @staticmethod
    def get_daily_report_html(day_name: str, formatted_date: str, records_present: bool,
                              user_activity: Dict[str, List[Dict[str, str]]], anomalies: List[str]) -> str:
        html = f"""
        <div style="margin-bottom: 20px;">
        """

        if not records_present:
            html += "<p style='font-size: 14px; color: #666; text-align: center; padding: 20px; background: #f9f9f9; border-radius: 4px;'><em>Sem registros de ponto neste dia.</em></p></div>"
        else:
            html += """
            <table style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px; color: #333; margin-bottom: 25px;">
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
                    # p['type'] will be 'E' or 'S'
                    color = "#2E7D32" if p['type'] == 'E' else "#EF6C00"
                    label = "Entrada" if p['type'] == 'E' else "Saída"
                    punches_html += f"""<span style="display: inline-block; background-color: {color}; color: #fff; padding: 4px 10px; border-radius: 14px; font-size: 13px; font-weight: bold; margin-right: 6px; margin-bottom: 4px;">{p['time']}</span>"""

                html += f"""
                <tr style="background-color: {bg_color}; border-bottom: 1px solid #eee;">
                    <td style="padding: 10px 8px;"><strong>{name}</strong></td>
                    <td style="padding: 10px 8px;">{punches_html}</td>
                </tr>
                """

            html += "</tbody></table>"

        if anomalies:
            html += """
            <div style="margin-top: 25px;">
                <h4 style="color: #D32F2F; margin-bottom: 10px; font-size: 16px;">Anomalias Detectadas</h4>
                <ul style="background-color: #fde8e8; padding: 15px 15px 15px 30px; border-radius: 4px; color: #D32F2F; font-size: 14px; margin: 0;">
            """
            for a in anomalies:
                html += f"<li style='margin-bottom: 5px;'>{a}</li>"
            html += "</ul></div>"

        html += "</div>"
        return html

    @staticmethod
    def get_backup_email_html(period_text: str, report_html: str) -> str:
        return f"""
        <html>
        <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; background-color: #f9f9f9;">
            <div style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #2c3e50; color: #ffffff; padding: 20px; text-align: center;">
                    <h2 style="margin: 0; font-size: 24px; font-weight: 500;">Resumo Operacional SPE</h2>
                </div>
                <div style="padding: 30px;">
                    <p style="font-size: 16px; margin-top: 0;">Prezados,</p>
                    <p style="font-size: 15px; color: #555;">{period_text}</p>
                    
                    {report_html}
                    
                </div>
                <div style="background-color: #f1f1f1; padding: 20px 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                    <p style="font-size: 14px; color: #777; margin: 0;">Atenciosamente,</p>
                    <p style="font-size: 15px; font-weight: bold; color: #555; margin: 5px 0 0 0;">SPE - Sistema de Ponto Eletrônico</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def get_payroll_email_html(action: str, user_name: str, user_email: str, month: int, year: int,
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
                                <td style="padding: 5px 0; font-weight: bold; color: {color};">{action}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0; color: #555;"><strong>Responsável:</strong></td>
                                <td style="padding: 5px 0;">{user_name} &lt;{user_email}&gt;</td>
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
