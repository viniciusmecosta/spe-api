import io
from reportlab.lib.styles import getSampleStyleSheet
import pytest
from datetime import date
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.services.timesheet_service import timesheet_service
from app.domain.models.user import User
from app.domain.models.enums import UserRole
from app.domain.models.company import Company
from app.domain.models.holiday import Holiday
from app.services.time_calculation_service import PeriodTimeResult, DailyTimeResult

def test_format_duration():
    assert timesheet_service._format_duration(3600) == '01:00'
    assert timesheet_service._format_duration(3660) == '01:01'
    assert timesheet_service._format_duration(0) == '00:00'

def test_format_cnpj():
    assert timesheet_service._format_cnpj('') == '-'
    assert timesheet_service._format_cnpj('12345678901234') == '12.345.678/9012-34'
    assert timesheet_service._format_cnpj('1234') == '1234'

def test_format_cpf():
    assert timesheet_service._format_cpf(None) == '-'
    assert timesheet_service._format_cpf('12345678901') == '123.456.789-01'
    assert timesheet_service._format_cpf('123') == '123'

def test_format_pis():
    assert timesheet_service._format_pis('') == '-'
    assert timesheet_service._format_pis('12345678901') == '123.45678.90-1'
    assert timesheet_service._format_pis('123') == '123'

def test_format_phone():
    assert timesheet_service._format_phone('') == '-'
    assert timesheet_service._format_phone('11987654321') == '(11) 98765-4321'
    assert timesheet_service._format_phone('1187654321') == '(11) 8765-4321'
    assert timesheet_service._format_phone('123') == '123'

def test_build_daily_records_table():
    mock_daily_1 = MagicMock(spec=DailyTimeResult)
    mock_daily_1.net_worked_seconds = 3600
    mock_daily_1.unapproved_extra_seconds = 0
    mock_daily_1.waiver_seconds = 1800
    mock_daily_1.extra_seconds = 0
    mock_daily_1.missing_seconds = 0
    mock_daily_1.punch_blocks = ['08:00 - 09:00']
    mock_daily_2 = MagicMock(spec=DailyTimeResult)
    mock_daily_2.net_worked_seconds = 3600
    mock_daily_2.unapproved_extra_seconds = 0
    mock_daily_2.waiver_seconds = 0
    mock_daily_2.extra_seconds = 0
    mock_daily_2.missing_seconds = 0
    mock_daily_2.punch_blocks = []
    period_result = MagicMock(spec=PeriodTimeResult)
    period_result.total_net_worked_seconds = 3600
    period_result.daily_results = {date(2023, 10, 1): mock_daily_1, date(2023, 10, 2): mock_daily_2}
    period_result.daily_is_holiday = {date(2023, 10, 1): False, date(2023, 10, 2): True}
    holiday = MagicMock(spec=Holiday)
    holiday.date = date(2023, 10, 2)
    holiday.name = 'Test Holiday'
    data_table = []
    t_style = []
    styles = getSampleStyleSheet()
    table_text_style = styles['Normal']
    t = timesheet_service._build_daily_records_table(date(2023, 10, 1), date(2023, 10, 2), period_result, [holiday], data_table, t_style, table_text_style)
    assert t is not None

def test_generate_user_timesheet_pdf_not_found(db_session_mock, mocker):
    mocker.patch('app.repositories.user_repository.user_repository.get', return_value=None)
    with pytest.raises(HTTPException) as excinfo:
        timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert excinfo.value.status_code == 404

def test_generate_user_timesheet_pdf_success(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User'
    mock_user.cpf = '12345678901'
    mock_user.pis = '12345678901'
    mock_user.role = UserRole.EMPLOYEE
    mock_user.historical_schedules = []
    mock_company = MagicMock(spec=Company)
    mock_company.name = 'Test Company'
    mock_company.cnpj = '12345678901234'
    mock_company.address = 'Test Addr'
    mock_company.phone = '11987654321'
    mock_company.logo_path = None
    mocker.patch('app.repositories.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.repositories.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.repositories.time_record_repository.time_record_repository.get_by_range', return_value=[])
    mocker.patch('app.repositories.holiday_repository.holiday_repository.get_by_month', return_value=[])
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.services.time_calculation_service.time_calculation_service.calculate_period_time')
    daily_res = {}
    daily_hol = {}
    for d in range(1, 32):
        dt = date(2023, 10, d)
        mock_daily = MagicMock(spec=DailyTimeResult)
        mock_daily.punch_blocks = []
        mock_daily.net_worked_seconds = 0
        mock_daily.unapproved_extra_seconds = 0
        mock_daily.waiver_seconds = 0
        mock_daily.extra_seconds = 0
        mock_daily.missing_seconds = 0
        daily_res[dt] = mock_daily
        daily_hol[dt] = False
    mock_period = MagicMock(spec=PeriodTimeResult)
    mock_period.total_net_worked_seconds = 3600
    mock_period.daily_results = daily_res
    mock_period.daily_is_holiday = daily_hol
    mock_calc.return_value = mock_period
    buffer = timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0

def test_generate_all_timesheets_pdf_zip_not_found(db_session_mock, mocker):
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.join.return_value.filter.return_value.distinct.return_value.filter.return_value.all.return_value = []
    with pytest.raises(HTTPException) as excinfo:
        timesheet_service.generate_all_timesheets_pdf_zip(db_session_mock, 10, 2023, [1])
    assert excinfo.value.status_code == 404

def test_generate_all_timesheets_pdf_zip_success(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User A'
    db_session_mock.query.return_value = MagicMock()
    query_mock = db_session_mock.query.return_value.join.return_value.filter.return_value.distinct.return_value
    query_mock.all.return_value = [mock_user]
    query_mock.filter.return_value.all.return_value = [mock_user]
    mock_pdf = mocker.patch('app.services.timesheet_service.timesheet_service.generate_user_timesheet_pdf')
    mock_pdf.return_value = io.BytesIO(b'dummy pdf content')
    buffer = timesheet_service.generate_all_timesheets_pdf_zip(db_session_mock, 10, 2023, None)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0

def test_generate_all_timesheets_pdf_zip_error_continue(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User A'
    db_session_mock.query.return_value = MagicMock()
    query_mock = db_session_mock.query.return_value.join.return_value.filter.return_value.distinct.return_value
    query_mock.all.return_value = [mock_user]
    query_mock.filter.return_value.all.return_value = [mock_user]
    mock_pdf = mocker.patch('app.services.timesheet_service.timesheet_service.generate_user_timesheet_pdf')
    mock_pdf.side_effect = ValueError('Test error')
    buffer = timesheet_service.generate_all_timesheets_pdf_zip(db_session_mock, 10, 2023, None)
    assert isinstance(buffer, io.BytesIO)

def test_generate_user_timesheet_pdf_with_logo_success(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User'
    mock_user.cpf = '12345678901'
    mock_user.pis = '12345678901'
    mock_user.role = UserRole.EMPLOYEE
    mock_user.historical_schedules = []
    mock_company = MagicMock(spec=Company)
    mock_company.name = 'Test Company'
    mock_company.cnpj = '12345678901234'
    mock_company.address = 'Test Addr'
    mock_company.phone = '11987654321'
    mock_company.logo_path = 'logo.png'
    mocker.patch('app.repositories.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.repositories.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.repositories.time_record_repository.time_record_repository.get_by_range', return_value=[])
    mocker.patch('app.repositories.holiday_repository.holiday_repository.get_by_month', return_value=[])
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('app.services.timesheet_service.Image')
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.services.time_calculation_service.time_calculation_service.calculate_period_time')
    daily_res = {}
    daily_hol = {}
    for d in range(1, 32):
        dt = date(2023, 10, d)
        mock_daily = MagicMock(spec=DailyTimeResult)
        mock_daily.punch_blocks = []
        mock_daily.net_worked_seconds = 0
        mock_daily.unapproved_extra_seconds = 0
        mock_daily.waiver_seconds = 0
        mock_daily.extra_seconds = 0
        mock_daily.missing_seconds = 0
        daily_res[dt] = mock_daily
        daily_hol[dt] = False
    mock_period = MagicMock(spec=PeriodTimeResult)
    mock_period.total_net_worked_seconds = 3600
    mock_period.daily_results = daily_res
    mock_period.daily_is_holiday = daily_hol
    mock_calc.return_value = mock_period
    buffer = timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0

def test_generate_user_timesheet_pdf_with_logo_not_found(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User'
    mock_user.cpf = '12345678901'
    mock_user.pis = '12345678901'
    mock_user.role = UserRole.EMPLOYEE
    mock_user.historical_schedules = []
    mock_company = MagicMock(spec=Company)
    mock_company.name = 'Test Company'
    mock_company.cnpj = '12345678901234'
    mock_company.address = 'Test Addr'
    mock_company.phone = '11987654321'
    mock_company.logo_path = 'logo.png'
    mocker.patch('app.repositories.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.repositories.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.repositories.time_record_repository.time_record_repository.get_by_range', return_value=[])
    mocker.patch('app.repositories.holiday_repository.holiday_repository.get_by_month', return_value=[])
    mocker.patch('os.path.exists', return_value=False)
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.services.time_calculation_service.time_calculation_service.calculate_period_time')
    daily_res = {}
    daily_hol = {}
    for d in range(1, 32):
        dt = date(2023, 10, d)
        mock_daily = MagicMock(spec=DailyTimeResult)
        mock_daily.punch_blocks = []
        mock_daily.net_worked_seconds = 0
        mock_daily.unapproved_extra_seconds = 0
        mock_daily.waiver_seconds = 0
        mock_daily.extra_seconds = 0
        mock_daily.missing_seconds = 0
        daily_res[dt] = mock_daily
        daily_hol[dt] = False
    mock_period = MagicMock(spec=PeriodTimeResult)
    mock_period.total_net_worked_seconds = 3600
    mock_period.daily_results = daily_res
    mock_period.daily_is_holiday = daily_hol
    mock_calc.return_value = mock_period
    buffer = timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0

def test_generate_user_timesheet_pdf_with_logo_os_error(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User'
    mock_user.cpf = '12345678901'
    mock_user.pis = '12345678901'
    mock_user.role = UserRole.EMPLOYEE
    mock_user.historical_schedules = []
    mock_company = MagicMock(spec=Company)
    mock_company.name = 'Test Company'
    mock_company.cnpj = '12345678901234'
    mock_company.address = 'Test Addr'
    mock_company.phone = '11987654321'
    mock_company.logo_path = 'logo.png'
    mocker.patch('app.repositories.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.repositories.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.repositories.time_record_repository.time_record_repository.get_by_range', return_value=[])
    mocker.patch('app.repositories.holiday_repository.holiday_repository.get_by_month', return_value=[])
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('reportlab.platypus.Image', side_effect=OSError('File not found'))
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.services.time_calculation_service.time_calculation_service.calculate_period_time')
    daily_res = {}
    daily_hol = {}
    for d in range(1, 32):
        dt = date(2023, 10, d)
        mock_daily = MagicMock(spec=DailyTimeResult)
        mock_daily.punch_blocks = []
        mock_daily.net_worked_seconds = 0
        mock_daily.unapproved_extra_seconds = 0
        mock_daily.waiver_seconds = 0
        mock_daily.extra_seconds = 0
        mock_daily.missing_seconds = 0
        daily_res[dt] = mock_daily
        daily_hol[dt] = False
    mock_period = MagicMock(spec=PeriodTimeResult)
    mock_period.total_net_worked_seconds = 3600
    mock_period.daily_results = daily_res
    mock_period.daily_is_holiday = daily_hol
    mock_calc.return_value = mock_period
    buffer = timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0
from reportlab.platypus import Paragraph, Table

def test_exhaustive_pdf_structural_generation(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Teste Funcionario Silva'
    mock_user.cpf = '12345678901'
    mock_user.pis = '12345678901'
    mock_user.role = UserRole.EMPLOYEE
    mock_user.historical_schedules = []
    mock_company = MagicMock(spec=Company)
    mock_company.name = 'Empregadora Master S.A.'
    mock_company.cnpj = '12345678901234'
    mock_company.address = 'Av Paulista 1000'
    mock_company.phone = '11987654321'
    mock_company.logo_path = None
    mocker.patch('app.repositories.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.repositories.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.repositories.time_record_repository.time_record_repository.get_by_range', return_value=[])
    mocker.patch('app.repositories.holiday_repository.holiday_repository.get_by_month', return_value=[])
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.services.time_calculation_service.time_calculation_service.calculate_period_time')
    daily_res = {}
    daily_hol = {}
    for d in range(1, 32):
        dt = date(2023, 10, d)
        mock_daily = MagicMock(spec=DailyTimeResult)
        mock_daily.punch_blocks = ['08:00 - 18:00'] if d == 15 else []
        mock_daily.net_worked_seconds = 36000 if d == 15 else 0
        mock_daily.unapproved_extra_seconds = 0
        mock_daily.waiver_seconds = 0
        mock_daily.extra_seconds = 0
        mock_daily.missing_seconds = 0
        daily_res[dt] = mock_daily
        daily_hol[dt] = d == 12
    mock_period = MagicMock(spec=PeriodTimeResult)
    mock_period.total_net_worked_seconds = 36000
    mock_period.daily_results = daily_res
    mock_period.daily_is_holiday = daily_hol
    mock_calc.return_value = mock_period
    captured_story = []

    def fake_build(story, onFirstPage=None, onLaterPages=None):
        captured_story.extend(story)
    mocker.patch('app.services.timesheet_service.SimpleDocTemplate.build', side_effect=fake_build)
    buffer = timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert len(captured_story) > 10, 'A story deve conter múltiplos elementos (Parágrafos e Tabelas)'
    paragraphs = [item for item in captured_story if isinstance(item, Paragraph)]
    tables = [item for item in captured_story if isinstance(item, Table)]
    texts = [p.getPlainText() for p in paragraphs]
    assert 'Empregadora Master S.A. - Registro de Ponto' in texts
    assert 'DADOS DA EMPRESA' in texts
    assert 'DADOS DO COLABORADOR' in texts
    assert len(tables) >= 5
    daily_table = None
    for t in tables:
        if len(t._cellvalues) == 32:
            daily_table = t
            break
    assert daily_table is not None, 'Tabela de ponto diário (com 31 dias) não foi encontrada'
    row_dia_12 = daily_table._cellvalues[12]
    assert '12/10/2023' in str(row_dia_12[0].getPlainText())
    assert 'Feriado' in str(row_dia_12[2].getPlainText())
    bg_style = [cmd for cmd in daily_table._bkgrndcmds if cmd[0] == 'BACKGROUND']
    assert len(bg_style) > 0, 'Deveria ter comando de Background color no header e finais de semana'