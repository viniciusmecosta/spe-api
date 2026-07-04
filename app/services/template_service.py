from typing import Dict, List


class TemplateService:
    @staticmethod
    def get_daily_report_html(day_name: str, formatted_date: str, records_present: bool,
                              user_activity: Dict[str, List[str]]) -> str:
        html = "<div style='margin-bottom: 20px;'>"
        html += f"<h3 style=\"color: #333; margin-bottom: 5px;\">Relatório de Pontos - {day_name}, {formatted_date}</h3>"

        if not records_present:
            html += "<p style='font-size: 13px; color: #666;'><em>Sem registros de ponto neste dia.</em></p></div>"
            return html

        html += "<table style=\"width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px; color: #333;\">"
        html += "<thead><tr style=\"background-color: #f4f4f4; text-align: left;\">"
        html += "<th style=\"padding: 8px; border: 1px solid #ddd; width: 40%;\">Colaborador</th>"
        html += "<th style=\"padding: 8px; border: 1px solid #ddd;\">Registros (E=Entrada, S=Saída)</th>"
        html += "</tr></thead><tbody>"

        for name, punches in user_activity.items():
            punches_str = "  |  ".join(punches)
            html += f"<tr><td style=\"padding: 8px; border: 1px solid #ddd;\"><strong>{name}</strong></td><td style=\"padding: 8px; border: 1px solid #ddd;\">{punches_str}</td></tr>"

        html += "</tbody></table>"
        html += "</div><hr style='border: 0; border-top: 1px solid #eee; margin: 20px 0;'>"
        return html

    @staticmethod
    def get_backup_email_html(period_text: str, report_html: str) -> str:
        return (
            f"<html><body style=\"font-family: Arial, sans-serif; color: #333;\">"
            f"<p>Prezados,</p>"
            f"<p>Seguem em anexo a cópia de segurança do banco de dados e os logs operacionais.</p>"
            f"<p>{period_text}</p>"
            f"<br>"
            f"{report_html}"
            f"<br>"
            f"<p style=\"font-size: 12px; color: #777;\">Atenciosamente,<br>SPE - Sistema de Ponto Eletrônico</p>"
            f"</body></html>"
        )


template_service = TemplateService()
