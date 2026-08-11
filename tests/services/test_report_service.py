import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from zoneinfo import ZoneInfo
from collections import defaultdict
from app.core.config import settings
from app.domain.models.enums import UserRole, RecordType
from app.domain.models.user import User
from app.domain.models.time_record import TimeRecord
from app.services.report_service import ReportService
from app.schemas.report import HistoryResponse, AdvancedUserReportResponse, MonthlyReportResponse, UserPayrollSummary, AdvancedUserReportResponse

@pytest.fixture
def service():
    return ReportService()

@pytest.fixture
def mock_repo_user():
    with patch('app.services.report_service.user_repository') as mock:
        yield mock

@pytest.fixture
def mock_repo_time_record():
    with patch('app.services.report_service.time_record_repository') as mock:
        yield mock

@pytest.fixture
def mock_repo_holiday():
    with patch('app.services.report_service.holiday_repository') as mock:
        yield mock

@pytest.fixture
def mock_anomaly_service():
    with patch('app.services.report_service.anomaly_service') as mock:
        yield mock

@pytest.fixture
def mock_time_calc_service():
    with patch('app.services.time_calculation_service.time_calculation_service') as mock:
        yield mock

@pytest.fixture
def mock_db(db_session_mock):
    return db_session_mock

def test_get_month_range(service):
    start, end = service._get_month_range(2, 2024)
    assert start == date(2024, 2, 1)
    assert end == date(2024, 2, 29)

def test_format_duration(service):
    assert service._format_duration(3600) == '01:00'
    assert service._format_duration(3660) == '01:01'
    assert service._format_duration(3599) == '01:00'
    assert service._format_duration(0) == '00:00'

def test_apply_employee_filters(service):
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    res = service._apply_employee_filters(mock_query, [1, 2])
    assert res == mock_query
    assert mock_query.filter.call_count == 3
    mock_query.reset_mock()
    res2 = service._apply_employee_filters(mock_query, None)
    assert mock_query.filter.call_count == 2

def _get_mock_period_result():
    period_result = MagicMock()
    daily_res_mock = MagicMock()
    daily_res_mock.net_worked_seconds = 3600
    daily_res_mock.waiver_seconds = 3600
    daily_res_mock.unapproved_extra_seconds = 0
    daily_res_mock.extra_seconds = 0
    daily_res_mock.missing_seconds = 25200
    daily_res_mock.entries = ['08:00']
    daily_res_mock.exits = []
    daily_res_mock.punches = ['08:00']
    period_result.daily_results = defaultdict(lambda: daily_res_mock)
    abono = MagicMock()
    abono.amount_hours = 1
    abono.id = 1
    period_result.daily_waivers = defaultdict(lambda: abono)
    period_result.daily_expected_seconds = defaultdict(lambda: 28800)
    return period_result

def test_build_history_day(service):
    current = date(2024, 1, 1)
    today_date = date(2024, 1, 2)
    rec1 = MagicMock(spec=TimeRecord)
    rec1.record_datetime = datetime(2024, 1, 1, 8, 0)
    rec1.id = 1
    rec1.record_type = RecordType.ENTRY
    rec1.ip_address = '127.0.0.1'
    rec1.device_name = 'test'
    rec1.platform = 'web'
    rec1.biometric_id = None
    rec1.editor_name = 'admin'
    rec1.edit_justification = 'fix'
    records = [rec1]
    hol1 = MagicMock()
    hol1.date = current
    hol1.name = 'Ano Novo'
    holidays = [hol1]
    anom1 = MagicMock()
    anom1.date = current
    anom1.description = 'Anomaly 1'
    anomalies = [anom1]
    period_result = _get_mock_period_result()
    res = service._build_history_day(current, today_date, records, holidays, anomalies, period_result, True)
    assert res.date == current
    assert res.is_holiday is True
    assert res.status == 'Normal'
    assert res.worked_time == '01:00'
    assert res.has_anomaly is True
    assert res.anomalies == ['Anomaly 1']
    assert len(res.punches) == 1
    res_no_records = service._build_history_day(current, today_date, [], holidays, anomalies, period_result, False)
    assert res_no_records.status == 'Feriado'
    res_weekend = service._build_history_day(date(2024, 1, 6), today_date, [], [], [], period_result, False)
    assert res_weekend.status == 'Fim de semana'
    res_abono = service._build_history_day(date(2024, 1, 2), today_date, [], [], [], period_result, False)
    assert res_abono.status == 'Abono'
    period_result.daily_waivers = defaultdict(lambda: None)
    res_today = service._build_history_day(today_date, today_date, [], [], [], period_result, False)
    assert res_today.status == ''
    res_falta = service._build_history_day(date(2024, 1, 1), today_date, [], [], [], period_result, False)
    assert res_falta.status == 'Falta'
    res_future = service._build_history_day(date(2024, 1, 3), today_date, [], [], anomalies, period_result, False)
    assert not res_future.has_anomaly

def test_build_detailed_punches(service):
    assert service._build_detailed_punches([], False) == []
    assert service._build_detailed_punches([MagicMock()], False) == []
    rec = MagicMock(spec=TimeRecord)
    rec.id = 1
    rec.record_datetime = datetime(2024, 1, 1, 8, 0)
    rec.record_type = RecordType.ENTRY
    rec.ip_address = '1.1.1.1'
    rec.device_name = 'test'
    rec.platform = 'web'
    rec.biometric_id = None
    rec.editor_name = 'admin'
    rec.edit_justification = 'fix'
    res = service._build_detailed_punches([rec], True)
    assert len(res) == 1
    assert res[0].id == 1

def test_determine_daily_status(service):
    assert service._determine_daily_status(True, True, False, False, 0, 0, False, False) == 'Feriado'
    assert service._determine_daily_status(True, False, True, False, 0, 0, False, False) == 'Fim de semana'
    assert service._determine_daily_status(True, False, False, False, 0, 0, False, False) == ''
    assert service._determine_daily_status(False, False, False, True, 0, 0, False, False) == 'Abono'
    assert service._determine_daily_status(False, True, False, False, 0, 0, False, False) == 'Feriado'
    assert service._determine_daily_status(False, False, True, False, 3600, 0, False, False) == 'Normal'
    assert service._determine_daily_status(False, False, True, False, 0, 0, False, False) == 'Fim de semana'
    assert service._determine_daily_status(False, False, False, False, 0, 3600, True, False) == ''
    assert service._determine_daily_status(False, False, False, False, 0, 3600, False, False) == 'Falta'
    assert service._determine_daily_status(False, False, False, False, 0, 0, False, False) == '-'
    assert service._determine_daily_status(False, False, False, False, 3600, 0, False, False) == 'Normal'
    assert service._determine_daily_status(False, False, False, False, 3600, 3600, False, True) == 'Normal'
    assert service._determine_daily_status(False, False, False, False, 0, 3600, False, True) == 'Falta'

def test_build_daily_report_item(service):
    current = date(2024, 1, 1)
    today_date = date(2024, 1, 2)
    rec1 = MagicMock(spec=TimeRecord)
    rec1.record_datetime = datetime(2024, 1, 1, 8, 0)
    rec1.id = 1
    rec1.record_type = RecordType.ENTRY
    rec1.ip_address = '127.0.0.1'
    rec1.device_name = 'test'
    rec1.platform = 'web'
    rec1.biometric_id = None
    rec1.editor_name = 'admin'
    rec1.edit_justification = None
    records = [rec1]
    hol1 = MagicMock()
    hol1.date = current
    hol1.name = 'Ano Novo'
    holidays = [hol1]
    period_result = _get_mock_period_result()
    res = service._build_daily_report_item(current, today_date, records, holidays, period_result, True, True)
    assert res.date == current
    assert res.is_holiday is True
    assert res.status == 'Abono'
    assert res.worked_hours == 1.0
    assert res.expected_hours == 8.0
    assert res.balance_hours == -7.0
    assert res.extra_hours == 0.0
    assert res.missing_hours == 7.0
    assert 'Abono: 01:00' in res.punches

def test_build_daily_report_item_no_schedule(service):
    current = date(2024, 1, 1)
    today_date = date(2024, 1, 1)
    period_result = _get_mock_period_result()
    period_result.daily_waivers = defaultdict(lambda: None)
    period_result.daily_results = defaultdict(lambda: MagicMock(extra_seconds=0, missing_seconds=0, waiver_seconds=0))
    res = service._build_daily_report_item(current, today_date, [], [], period_result, False, False)
    assert res.balance_hours == 0.0
    assert res.status == 'Normal'

def test_get_history_report_future_month(service, mock_db, mock_repo_user):
    tz = ZoneInfo(settings.TIMEZONE)
    now = datetime.now(tz)
    future_year = now.year + 1
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.EMPLOYEE
    current_user = user
    res = service.get_history_report(mock_db, 1, 1, future_year, current_user)
    assert res.total_worked_time == '00:00'
    assert len(res.days) == 0

def test_get_history_report_user_not_found(service, mock_db, mock_repo_user):
    mock_repo_user.get.return_value = None
    current_user = MagicMock(spec=User)
    current_user.id = 2
    with pytest.raises(HTTPException) as exc:
        service.get_history_report(mock_db, 1, None, None, current_user)
    assert exc.value.status_code == 404

def test_get_history_report_success(service, mock_db, mock_repo_user, mock_repo_time_record, mock_repo_holiday, mock_anomaly_service, mock_time_calc_service):
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.EMPLOYEE
    user.historical_schedules = []
    mock_repo_user.get.return_value = user
    current_user = user
    mock_repo_time_record.get_by_range.return_value = []
    mock_repo_holiday.get_by_month.return_value = []
    mock_anomaly_service.get_anomalies.return_value = []
    period_result = _get_mock_period_result()
    period_result.total_net_worked_seconds = 3600
    mock_time_calc_service.calculate_period_time.return_value = period_result
    res = service.get_history_report(mock_db, 1, 1, 2024, current_user)
    assert res.total_worked_time == '01:00'

def test_get_advanced_user_report_not_found(service, mock_db, mock_repo_user):
    mock_repo_user.get.return_value = None
    res = service.get_advanced_user_report(mock_db, 1, 1, 2024)
    assert res is None

def test_get_advanced_user_report_success(service, mock_db, mock_repo_user, mock_repo_time_record, mock_repo_holiday, mock_time_calc_service):
    user = MagicMock(spec=User)
    user.id = 1
    user.name = 'Test'
    user.role = UserRole.EMPLOYEE
    user.historical_schedules = []
    mock_repo_user.get.return_value = user
    current_user = MagicMock(spec=User)
    current_user.role = UserRole.MAINTAINER
    mock_repo_time_record.get_by_range.return_value = []
    mock_repo_holiday.get_by_month.return_value = []
    period_result = _get_mock_period_result()
    period_result.total_net_worked_seconds = 3600
    period_result.total_expected_seconds = 28800
    period_result.daily_waivers = defaultdict(lambda: None)
    daily_res_mock = MagicMock()
    daily_res_mock.net_worked_seconds = 3600
    daily_res_mock.waiver_seconds = 0
    daily_res_mock.unapproved_extra_seconds = 0
    daily_res_mock.entries = []
    daily_res_mock.exits = []
    daily_res_mock.punches = []
    period_result.daily_results = defaultdict(lambda: daily_res_mock)
    mock_time_calc_service.calculate_period_time.return_value = period_result
    res = service.get_advanced_user_report(mock_db, 1, 1, 2024, current_user)
    assert res.summary.total_worked_time == '01:00'
    assert res.summary.total_expected_time == '08:00'

def test_get_advanced_user_report_absences_and_extras(service, mock_db, mock_repo_user, mock_time_calc_service):
    user = MagicMock(spec=User)
    user.id = 1
    user.name = 'Test'
    user.role = UserRole.EMPLOYEE
    user.historical_schedules = [MagicMock()]
    mock_repo_user.get.return_value = user
    period_result = _get_mock_period_result()
    period_result.total_net_worked_seconds = 0
    period_result.total_expected_seconds = 28800
    period_result.daily_waivers = defaultdict(lambda: None)
    daily_res_mock = MagicMock()
    daily_res_mock.net_worked_seconds = 0
    daily_res_mock.waiver_seconds = 0
    daily_res_mock.unapproved_extra_seconds = 0
    daily_res_mock.entries = []
    daily_res_mock.exits = []
    daily_res_mock.punches = []
    period_result.daily_results = defaultdict(lambda: daily_res_mock)
    mock_time_calc_service.calculate_period_time.return_value = period_result
    res = service.get_advanced_user_report(mock_db, 1, 1, 2024, None)
    assert res.summary.absences > 0

def test_get_monthly_summary(service, mock_db):
    user = MagicMock(spec=User)
    user.id = 1
    user.name = 'Test'
    user.role = UserRole.EMPLOYEE
    user.historical_schedules = []
    def mock_query_side_effect(model):
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        if getattr(model, '__name__', '') == 'User':
            mock_query.all.return_value = [user]
        else:
            mock_query.all.return_value = []
        return mock_query
    mock_db.query.side_effect = mock_query_side_effect
    with patch.object(service, 'get_advanced_user_report') as mock_adv_report:
        adv_res = MagicMock()
        adv_res.summary = UserPayrollSummary(user_id=1, user_name='Test', total_worked_time='01:00', total_expected_time='08:00', total_worked_minutes=60, total_expected_minutes=480, days_worked=1, absences=0, total_worked_hours=1.0, total_expected_hours=8.0, total_extra_hours=0.0, total_missing_hours=7.0, final_balance=-7.0)
        mock_adv_report.return_value = adv_res
        res = service.get_monthly_summary(mock_db, 1, 2024, [1])
        assert res.month == 1
        assert res.year == 2024
        assert len(res.payroll_data) == 1

def test_get_monthly_summary_no_minutes(service, mock_db):
    user = MagicMock(spec=User)
    user.id = 1
    user.name = 'Test'
    user.role = UserRole.EMPLOYEE
    user.historical_schedules = []
    def mock_query_side_effect(model):
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        if getattr(model, '__name__', '') == 'User':
            mock_query.all.return_value = [user]
        else:
            mock_query.all.return_value = []
        return mock_query
    mock_db.query.side_effect = mock_query_side_effect
    with patch.object(service, 'get_advanced_user_report') as mock_adv_report:
        adv_res = MagicMock()
        adv_res.summary = UserPayrollSummary(user_id=1, user_name='Test', total_worked_time='00:00', total_expected_time='08:00', total_worked_minutes=0, total_expected_minutes=480, days_worked=0, absences=0, total_worked_hours=0.0, total_expected_hours=8.0, total_extra_hours=0.0, total_missing_hours=8.0, final_balance=-8.0)
        mock_adv_report.return_value = adv_res
        res = service.get_monthly_summary(mock_db, 1, 2024, [1])
        assert len(res.payroll_data) == 0

def test_locale_error():
    import locale
    import importlib
    import app.services.report_service as rs
    with patch('locale.setlocale', side_effect=locale.Error):
        importlib.reload(rs)
    importlib.reload(rs)

@pytest.mark.parametrize('is_future,is_holiday,is_weekend,is_waiver,worked_seconds,expected_seconds,is_today,has_schedule,expected', [(True, True, False, False, 0, 28800, False, True, 'Feriado'), (True, False, True, False, 0, 0, False, True, 'Fim de semana'), (True, False, False, False, 0, 28800, False, True, ''), (False, False, False, True, 0, 28800, False, True, 'Abono'), (False, True, False, True, 0, 28800, False, True, 'Abono'), (False, True, False, False, 0, 28800, False, True, 'Feriado'), (False, True, False, False, 3600, 28800, False, True, 'Feriado'), (False, False, True, False, 3600, 0, False, True, 'Normal'), (False, False, True, False, 0, 0, False, True, 'Fim de semana'), (False, False, False, False, 0, 28800, True, True, ''), (False, False, False, False, 0, 28800, False, True, 'Falta'), (False, False, False, False, 0, 0, False, False, '-'), (False, False, False, False, 3600, 0, False, False, 'Normal'), (False, False, False, False, 28800, 28800, False, True, 'Normal'), (False, False, False, False, 14400, 28800, False, True, 'Normal')])
def test_exhaustive_determine_daily_status(service, is_future, is_holiday, is_weekend, is_waiver, worked_seconds, expected_seconds, is_today, has_schedule, expected):
    """Garante que a lógica de negócio para a definição do status diário (Falta, Feriado, Fim de semana, etc.) nunca mude."""
    assert service._determine_daily_status(is_future, is_holiday, is_weekend, is_waiver, worked_seconds, expected_seconds, is_today, has_schedule) == expected

def test_exhaustive_build_daily_report_item(service):
    """Testa o item de relatório diário construindo cenários perfeitamente controlados e validando dados sensíveis como cálculo de banco de horas (saldo)."""
    current = date(2023, 10, 10)
    today_date = date(2023, 10, 15)
    daily_res_mock = MagicMock()
    daily_res_mock.net_worked_seconds = 9 * 3600
    daily_res_mock.unapproved_extra_seconds = 0
    daily_res_mock.waiver_seconds = 0
    daily_res_mock.extra_seconds = 3600
    daily_res_mock.missing_seconds = 0
    daily_res_mock.entries = ['08:00']
    daily_res_mock.exits = ['18:00']
    daily_res_mock.punches = ['08:00', '12:00', '13:00', '18:00']
    period_result = MagicMock()
    period_result.daily_results = {current: daily_res_mock}
    period_result.daily_waivers = {current: None}
    period_result.daily_expected_seconds = {current: 8 * 3600}
    item = service._build_daily_report_item(current, today_date, [], [], period_result, True, False)
    assert item.status == 'Normal'
    assert item.worked_hours == 9.0
    assert item.expected_hours == 8.0
    assert item.balance_hours == 1.0
    assert item.extra_hours == 1.0
    assert item.missing_hours == 0.0
    assert item.worked_minutes == 9 * 60
    assert item.worked_time == '09:00'
    daily_res_mock.net_worked_seconds = 7 * 3600
    daily_res_mock.extra_seconds = 0
    daily_res_mock.missing_seconds = 3600
    item2 = service._build_daily_report_item(current, today_date, [], [], period_result, True, False)
    assert item2.balance_hours == -1.0
    assert item2.missing_hours == 1.0
    daily_res_mock.waiver_seconds = 3600
    abono = MagicMock()
    abono.id = 99
    period_result.daily_waivers = {current: abono}
    item3 = service._build_daily_report_item(current, today_date, [], [], period_result, True, False)
    assert item3.status == 'Abono'
    assert 'Abono: 01:00' in item3.punches