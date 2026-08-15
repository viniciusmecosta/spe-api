from app.features.reports.template_service import TemplateService, template_service

def test_generate_punches_html_even_punches(db_session_mock):
    user_activity = {
        "User 1": [
            {"time": "08:00", "type": "E"},
            {"time": "12:00", "type": "S"}
        ]
    }
    result = TemplateService._generate_punches_html(user_activity)
    assert "User 1" in result
    assert "#ffffff" in result
    assert "#2E7D32" in result
    assert "#EF6C00" in result
    assert "08:00" in result
    assert "12:00" in result

def test_generate_punches_html_odd_punches():
    user_activity = {
        "User 2": [
            {"time": "08:00", "type": "E"}
        ]
    }
    result = TemplateService._generate_punches_html(user_activity)
    assert "User 2" in result
    assert "#fffbf0" in result

def test_generate_anomalies_html_empty():
    result = TemplateService._generate_anomalies_html([])
    assert result == ""

def test_generate_anomalies_html_with_anomalies():
    anomalies = ["Anomaly 1", "Anomaly 2"]
    result = TemplateService._generate_anomalies_html(anomalies)
    assert "Anomalias Detectadas" in result
    assert "Anomaly 1" in result
    assert "Anomaly 2" in result

def test_get_daily_report_html_no_records():
    result = TemplateService.get_daily_report_html("Segunda", "2023-10-10", False, {}, [])
    assert "Sem registros de ponto neste dia." in result

def test_get_daily_report_html_with_records():
    user_activity = {
        "User 1": [{"time": "08:00", "type": "E"}]
    }
    anomalies = ["Anomaly 1"]
    result = TemplateService.get_daily_report_html("Segunda", "2023-10-10", True, user_activity, anomalies)
    assert "User 1" in result
    assert "Anomaly 1" in result

def test_get_backup_email_html():
    result = TemplateService.get_backup_email_html("Period Text", "<p>Report HTML</p>")
    assert "Resumo Operacional SPE" in result
    assert "Period Text" in result
    assert "<p>Report HTML</p>" in result

def test_get_payroll_email_html_reabertura():
    result = TemplateService.get_payroll_email_html("Reabertura", "Admin", 10, 2023, "10/11/2023 10:00")
    assert "#e65100" in result
    assert "Folha Reaberta" in result
    assert "Reabertura" in result
    assert "Admin" in result
    assert "10/2023" in result
    assert "10/11/2023 10:00" in result
    assert "desbloqueadas" in result

def test_get_payroll_email_html_fechamento():
    result = TemplateService.get_payroll_email_html("Fechamento", "Admin2", 11, 2023, "10/12/2023 10:00")
    assert "#1565c0" in result
    assert "Folha Fechada" in result
    assert "Fechamento" in result
    assert "Admin2" in result
    assert "11/2023" in result
    assert "10/12/2023 10:00" in result
    assert "segue em anexo" in result

def test_template_service_instance():
    assert isinstance(template_service, TemplateService)
