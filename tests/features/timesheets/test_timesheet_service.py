import io
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import pytest
from app.features.companies.company_models import Company
from app.features.holidays.holiday_models import Holiday
from app.features.timesheets.timesheet_exceptions import (
    NoTimesheetRecordsFoundError,
    TimesheetUserNotFoundError,
)
from app.features.timesheets.timesheet_service import timesheet_service
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared.enums import UserRole
from app.shared.time_calculation_service import PeriodTimeResult, DailyTimeResult


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
    t = timesheet_service._build_daily_records_table(date(2023, 10, 1), date(2023, 10, 2), period_result, [holiday],
                                                     data_table, t_style, table_text_style)
    assert t is not None


@pytest.mark.asyncio
async def test_generate_user_timesheet_pdf_not_found(db_session_mock, mocker):
    mocker.patch('app.features.users.user_repository.user_repository.get', return_value=None)
    with pytest.raises(TimesheetUserNotFoundError) as excinfo:
        await timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_user_timesheet_pdf_success(db_session_mock, mocker):
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
    mocker.patch('app.features.users.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.features.companies.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.features.time_records.time_record_repository.time_record_repository.get_by_range',
                 return_value=[])
    mocker.patch('app.features.holidays.holiday_repository.holiday_repository.get_by_month', return_value=[])
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.shared.time_calculation_service.time_calculation_service.calculate_period_time')
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
    buffer = await timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0


@pytest.mark.asyncio
async def test_generate_all_timesheets_pdf_zip_not_found(db_session_mock, mocker):
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.join.return_value.filter.return_value.distinct.return_value.filter.return_value.all.return_value = []
    with pytest.raises(NoTimesheetRecordsFoundError) as excinfo:
        await timesheet_service.generate_all_timesheets_pdf_zip(db_session_mock, 10, 2023, [1])
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_all_timesheets_pdf_zip_success(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User A'
    db_session_mock.query.return_value = MagicMock()
    query_mock = db_session_mock.query.return_value.join.return_value.filter.return_value.distinct.return_value
    query_mock.all.return_value = [mock_user]
    query_mock.filter.return_value.all.return_value = [mock_user]
    mock_pdf = mocker.patch('app.features.timesheets.timesheet_service.timesheet_service.generate_user_timesheet_pdf',
                            new_callable=AsyncMock)
    mock_pdf.return_value = io.BytesIO(b'dummy pdf content')
    buffer = await timesheet_service.generate_all_timesheets_pdf_zip(db_session_mock, 10, 2023, None)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0


@pytest.mark.asyncio
async def test_generate_all_timesheets_pdf_zip_error_continue(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Test User A'
    db_session_mock.query.return_value = MagicMock()
    query_mock = db_session_mock.query.return_value.join.return_value.filter.return_value.distinct.return_value
    query_mock.all.return_value = [mock_user]
    query_mock.filter.return_value.all.return_value = [mock_user]
    mock_pdf = mocker.patch('app.features.timesheets.timesheet_service.timesheet_service.generate_user_timesheet_pdf',
                            new_callable=AsyncMock)
    mock_pdf.side_effect = ValueError('Test error')
    buffer = await timesheet_service.generate_all_timesheets_pdf_zip(db_session_mock, 10, 2023, None)
    assert isinstance(buffer, io.BytesIO)


@pytest.mark.asyncio
async def test_generate_user_timesheet_pdf_with_logo_success(db_session_mock, mocker):
    from reportlab.platypus import Flowable
    class DummyLogo(Flowable):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.width = 50
            self.height = 50

        def wrap(self, availWidth, availHeight):
            return self.width, self.height

        def draw(self):
            pass

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
    mocker.patch('app.features.users.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.features.companies.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.features.time_records.time_record_repository.time_record_repository.get_by_range',
                 return_value=[])
    mocker.patch('app.features.holidays.holiday_repository.holiday_repository.get_by_month', return_value=[])
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('app.features.timesheets.timesheet_service.Image', side_effect=DummyLogo)
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.shared.time_calculation_service.time_calculation_service.calculate_period_time')
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
    buffer = await timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0


@pytest.mark.asyncio
async def test_generate_user_timesheet_pdf_with_logo_not_found(db_session_mock, mocker):
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
    mocker.patch('app.features.users.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.features.companies.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.features.time_records.time_record_repository.time_record_repository.get_by_range',
                 return_value=[])
    mocker.patch('app.features.holidays.holiday_repository.holiday_repository.get_by_month', return_value=[])
    mocker.patch('os.path.exists', return_value=False)
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.shared.time_calculation_service.time_calculation_service.calculate_period_time')
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
    buffer = await timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0


@pytest.mark.asyncio
async def test_generate_user_timesheet_pdf_with_logo_os_error(db_session_mock, mocker):
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
    mocker.patch('app.features.users.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.features.companies.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.features.time_records.time_record_repository.time_record_repository.get_by_range',
                 return_value=[])
    mocker.patch('app.features.holidays.holiday_repository.holiday_repository.get_by_month', return_value=[])
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('app.features.timesheets.timesheet_service.Image', side_effect=OSError('File not found'))
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.shared.time_calculation_service.time_calculation_service.calculate_period_time')
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
    buffer = await timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)
    assert len(buffer.getvalue()) > 0


from reportlab.platypus import Paragraph, Table


@pytest.mark.asyncio
async def test_exhaustive_pdf_structural_generation(db_session_mock, mocker):
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
    mocker.patch('app.features.users.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.features.companies.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.features.time_records.time_record_repository.time_record_repository.get_by_range',
                 return_value=[])
    mocker.patch('app.features.holidays.holiday_repository.holiday_repository.get_by_month', return_value=[])
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []
    mock_calc = mocker.patch('app.shared.time_calculation_service.time_calculation_service.calculate_period_time')
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

    mocker.patch('app.features.timesheets.timesheet_service.SimpleDocTemplate.build', side_effect=fake_build)
    buffer = await timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
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
    assert str(row_dia_12[1].getPlainText()) in ['Quinta', 'Quinta-feira', 'Qui']
    bg_style = [cmd for cmd in daily_table._bkgrndcmds if cmd[0] == 'BACKGROUND']
    assert len(bg_style) > 0, 'Deveria ter comando de Background color no header e finais de semana'


def test_format_day_groups():
    assert timesheet_service._format_day_groups([]) == ""
    assert timesheet_service._format_day_groups([0]) == "Segunda"
    assert timesheet_service._format_day_groups([0, 1]) == "Segunda e Terça"
    assert timesheet_service._format_day_groups([0, 1, 2, 3, 4]) == "Segunda a Sexta"
    assert timesheet_service._format_day_groups([0, 1, 3, 4, 6]) == "Segunda e Terça, Quinta e Sexta e Domingo"


def test_get_schedule_transitions_and_grouping():
    user = MagicMock(spec=User)
    sch1 = MagicMock(spec=UserWorkScheduleConfig)
    sch1.valid_from = date(2023, 10, 10)
    sch1.valid_until = date(2023, 10, 20)
    user.historical_schedules = [sch1]
    transitions = timesheet_service._get_schedule_transitions(user, date(2023, 10, 1), date(2023, 10, 31))
    assert date(2023, 10, 10) in transitions
    assert date(2023, 10, 21) in transitions

    periods = timesheet_service._group_schedules_by_period(user,
                                                           [date(2023, 10, 1), date(2023, 10, 10), date(2023, 10, 5),
                                                            date(2023, 10, 31)])
    assert len(periods) > 0


def test_build_work_schedules_section_empty_periods(mocker):
    story = []
    style_heading = ParagraphStyle('H', fontSize=10)
    style_header = ParagraphStyle('T', fontSize=10)
    user = MagicMock(spec=User)
    sch = MagicMock(spec=UserWorkScheduleConfig)
    sch.valid_from = date(2023, 10, 1)
    sch.valid_until = date(2023, 10, 31)
    user.historical_schedules = [sch]
    mocker.patch.object(timesheet_service, '_group_schedules_by_period', return_value=[])
    timesheet_service._build_work_schedules_section(story, user, date(2023, 10, 1), date(2023, 10, 31), style_heading,
                                                    style_header)
    assert len(story) == 0


def test_build_work_schedules_section_branches():
    story = []
    style_heading = ParagraphStyle('H', fontSize=10)
    style_header = ParagraphStyle('T', fontSize=10)

    timesheet_service._build_work_schedules_section(story, None, date(2023, 10, 1), date(2023, 10, 31), style_heading,
                                                    style_header)
    assert len(story) == 0

    user = MagicMock(spec=User)
    user.historical_schedules = []
    timesheet_service._build_work_schedules_section(story, user, date(2023, 10, 1), date(2023, 10, 31), style_heading,
                                                    style_header)
    assert len(story) == 0

    sch_empty = MagicMock(spec=UserWorkScheduleConfig)
    sch_empty.valid_from = date(2023, 10, 1)
    sch_empty.valid_until = date(2023, 10, 31)
    sch_empty.entry_1 = None
    sch_empty.exit_1 = None
    sch_empty.entry_2 = None
    sch_empty.exit_2 = None
    user.historical_schedules = [sch_empty]
    timesheet_service._build_work_schedules_section(story, user, date(2023, 10, 1), date(2023, 10, 31), style_heading,
                                                    style_header)
    assert any(isinstance(item, Table) for item in story)

    story.clear()
    sch_active = MagicMock(spec=UserWorkScheduleConfig)
    sch_active.valid_from = date(2023, 10, 1)
    sch_active.valid_until = date(2023, 10, 15)
    sch_active.day_of_week = 0
    sch_active.entry_1 = time(8, 0)
    sch_active.exit_1 = time(12, 0)
    sch_active.entry_2 = time(13, 0)
    sch_active.exit_2 = time(17, 0)

    sch_active2 = MagicMock(spec=UserWorkScheduleConfig)
    sch_active2.valid_from = date(2023, 10, 16)
    sch_active2.valid_until = date(2023, 10, 31)
    sch_active2.day_of_week = 1
    sch_active2.entry_1 = time(9, 0)
    sch_active2.exit_1 = time(18, 0)
    sch_active2.entry_2 = None
    sch_active2.exit_2 = None

    user.historical_schedules = [sch_active, sch_active2]
    timesheet_service._build_work_schedules_section(story, user, date(2023, 10, 1), date(2023, 10, 31), style_heading,
                                                    style_header)
    assert any(isinstance(item, Table) for item in story)


@pytest.mark.asyncio
async def test_generate_user_timesheet_pdf_with_schedules(db_session_mock, mocker):
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.name = 'Funcionario Com Expediente'
    mock_user.cpf = '12345678901'
    mock_user.pis = '12345678901'
    mock_user.role = UserRole.EMPLOYEE

    sch = MagicMock(spec=UserWorkScheduleConfig)
    sch.valid_from = date(2023, 10, 1)
    sch.valid_until = date(2023, 10, 31)
    sch.day_of_week = 0
    sch.entry_1 = time(8, 0)
    sch.exit_1 = time(17, 0)
    sch.entry_2 = None
    sch.exit_2 = None
    mock_user.historical_schedules = [sch]

    mock_company = MagicMock(spec=Company)
    mock_company.name = 'Empresa'
    mock_company.cnpj = '12345678901234'
    mock_company.address = 'Rua'
    mock_company.phone = '11987654321'
    mock_company.logo_path = None

    mocker.patch('app.features.users.user_repository.user_repository.get', return_value=mock_user)
    mocker.patch('app.features.companies.company_repository.company_repository.get_current', return_value=mock_company)
    mocker.patch('app.features.time_records.time_record_repository.time_record_repository.get_by_range',
                 return_value=[])
    mocker.patch('app.features.holidays.holiday_repository.holiday_repository.get_by_month', return_value=[])
    db_session_mock.query.return_value = MagicMock()
    db_session_mock.query.return_value.filter.return_value.all.return_value = []

    mock_calc = mocker.patch('app.shared.time_calculation_service.time_calculation_service.calculate_period_time')
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

    buffer = await timesheet_service.generate_user_timesheet_pdf(db_session_mock, 1, 10, 2023)
    assert isinstance(buffer, io.BytesIO)


def test_draw_company_header_and_notes(mocker):
    from app.features.companies.company_models import Company
    mock_company = MagicMock(spec=Company)
    mock_company.name = 'Test Company'
    mock_company.cnpj = '12345678901234'
    mock_company.address = 'Test Addr'
    mock_company.phone = '11987654321'
    mock_company.logo_path = None

    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'])
    section_heading_style = ParagraphStyle('Section', parent=styles['Normal'])
    header_style = ParagraphStyle('Header', parent=styles['Normal'])

    timesheet_service._draw_company_header(story, mock_company, title_style, section_heading_style, header_style)

    found_table = False
    for item in story:
        if isinstance(item, Table):
            found_table = True
            cell_texts = []
            for row in item._cellvalues:
                for cell in row:
                    if hasattr(cell, 'text'):
                        cell_texts.append(cell.text)
            assert any('Razão Social:' in t for t in cell_texts)
    assert found_table
