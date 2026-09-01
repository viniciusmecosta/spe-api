import importlib
import locale
from collections import defaultdict
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.reports.report_exceptions import (
    EmployeePreviousMonthOnlyError,
    PayrollNotClosedForReportError,
    PendingAdjustmentsExistError,
    ReportAccessDeniedError,
    ReportExportPermissionError,
    ReportGlobalPermissionError,
    ReportNotFoundOrIncompleteError,
    ReportUserNotFoundError,
)
from app.features.reports.report_service import ReportService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.enums import AdjustmentStatus, RecordType, UserRole
from app.shared.time_calculation_service import (
    DailyAccountedResult,
    DailyTimeResult,
    PeriodTimeResult,
)


@pytest.fixture
def service():
    return ReportService()


@pytest.fixture
def mock_repo_user():
    with patch("app.features.reports.report_service.user_repository") as mock:
        yield mock


@pytest.fixture
def mock_repo_time_record():
    with patch("app.features.reports.report_service.time_record_repository") as mock:
        yield mock


@pytest.fixture
def mock_repo_holiday():
    with patch("app.features.reports.report_service.holiday_repository") as mock:
        yield mock


@pytest.fixture
def mock_anomaly_service():
    with patch("app.features.reports.report_service.anomaly_service") as mock:
        yield mock


@pytest.fixture
def mock_time_calc_service():
    with patch("app.shared.time_calculation_service.time_calculation_service") as mock:
        mock.calculate_accounted_time.return_value = DailyAccountedResult(
            raw_seconds=28800.0,
            excess_work_seconds=0.0,
            excess_lunch_seconds=0.0,
            early_return_seconds=0.0,
            total_excess_seconds=0.0,
            approved_seconds=0.0,
            accounted_seconds=28800.0,
            has_schedule=True,
            has_lunch_rule=False,
        )
        yield mock


@pytest.fixture
def mock_db(db_session_mock):
    return db_session_mock


def _create_daily_time_result(net_worked_seconds=28800.0, extra_seconds=0.0, missing_seconds=0.0,
                              waiver_seconds=0.0, unapproved_extra_seconds=0.0,
                              entries=None, exits=None, punches=None):
    return DailyTimeResult(
        raw_worked_seconds=net_worked_seconds,
        waiver_seconds=waiver_seconds,
        unapproved_extra_seconds=unapproved_extra_seconds,
        net_worked_seconds=net_worked_seconds,
        gross_worked_seconds=net_worked_seconds,
        extra_seconds=extra_seconds,
        missing_seconds=missing_seconds,
        entries=entries or ["08:00"],
        exits=exits or ["17:00"],
        punches=punches or ["08:00", "17:00"],
        punch_blocks=["08:00 - 17:00"],
    )


def test_get_month_range_all_months(service):
    start, end = service.get_month_range(1, 2024)
    assert start == date(2024, 1, 1)
    assert end == date(2024, 1, 31)

    start, end = service.get_month_range(2, 2024)
    assert start == date(2024, 2, 1)
    assert end == date(2024, 2, 29)

    start, end = service.get_month_range(2, 2023)
    assert start == date(2023, 2, 1)
    assert end == date(2023, 2, 28)

    start, end = service.get_month_range(4, 2024)
    assert start == date(2024, 4, 1)
    assert end == date(2024, 4, 30)

    start, end = service.get_month_range(12, 2024)
    assert start == date(2024, 12, 1)
    assert end == date(2024, 12, 31)


def test_get_month_range_invalid_month_13(service):
    with pytest.raises(ValueError):
        service.get_month_range(13, 2024)


def test_get_month_range_invalid_month_0(service):
    with pytest.raises(ValueError):
        service.get_month_range(0, 2024)


def test_format_duration_cases(service):
    assert service._format_duration(0) == "00:00"
    assert service._format_duration(30) == "00:00"
    assert service._format_duration(59) == "00:01"
    assert service._format_duration(60) == "00:01"
    assert service._format_duration(3599) == "01:00"
    assert service._format_duration(3600) == "01:00"
    assert service._format_duration(3660) == "01:01"
    assert service._format_duration(36000) == "10:00"
    assert service._format_duration(360000) == "100:00"


def test_apply_employee_filters(service):
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    filtered_query = service.apply_employee_filters(query_mock, employee_ids=[1, 2, 3])
    assert query_mock.filter.call_count == 3
    assert filtered_query is query_mock

    query_mock2 = MagicMock()
    query_mock2.filter.return_value = query_mock2
    filtered_query2 = service.apply_employee_filters(query_mock2, employee_ids=None)
    assert query_mock2.filter.call_count == 2
    assert filtered_query2 is query_mock2


def test_build_history_punches_manager_and_employee(service):
    editor_user = User(id=9, name="Admin")
    rec1 = TimeRecord(
        id=10,
        record_datetime=datetime(2024, 1, 1, 8, 30),
        record_type=RecordType.ENTRY,
        ip_address="192.168.1.50",
        device_name="Relogio 1",
        platform="WEB",
        biometric_id=1,
        editor=editor_user,
        edit_justification="Correcao",
    )
    rec2 = TimeRecord(
        id=11,
        record_datetime=datetime(2024, 1, 1, 17, 30),
        record_type=RecordType.EXIT,
        ip_address="192.168.1.50",
        device_name="Relogio 1",
        platform="WEB",
    )

    punches_emp = service._build_history_punches([rec1, rec2], is_manager=False)
    assert len(punches_emp) == 2
    assert punches_emp[0].id == 10
    assert punches_emp[0].time == "08:30"
    assert punches_emp[0].record_type == "ENTRY"
    assert punches_emp[0].ip_address is None

    punches_mgr = service._build_history_punches([rec1, rec2], is_manager=True)
    assert len(punches_mgr) == 2
    assert punches_mgr[0].id == 10
    assert punches_mgr[0].ip_address == "192.168.1.50"
    assert punches_mgr[0].device_name == "Relogio 1"
    assert punches_mgr[0].platform == "WEB"
    assert punches_mgr[0].edited_by == "Admin"
    assert punches_mgr[0].edit_justification == "Correcao"
    assert punches_mgr[1].edit_justification is None


def test_determine_history_status(service):
    assert service._determine_history_status(True, False, False, False, False) == "Normal"
    assert service._determine_history_status(True, True, True, True, True) == "Normal"
    assert service._determine_history_status(False, True, False, False, False) == "Feriado"
    assert service._determine_history_status(False, False, True, False, False) == "Fim de semana"
    assert service._determine_history_status(False, False, False, True, False) == "Abono"
    assert service._determine_history_status(False, False, False, False, True) == ""
    assert service._determine_history_status(False, False, False, False, False) == "Falta"


def test_build_history_day_scenarios(service):
    curr = date(2024, 1, 1)
    today = date(2024, 1, 15)

    rec = TimeRecord(
        id=1,
        record_datetime=datetime(2024, 1, 1, 8, 0),
        record_type=RecordType.ENTRY,
    )
    holiday = Holiday(date=curr, name="Ano Novo")
    anomaly = MagicMock()
    anomaly.date = curr
    anomaly.description = "Entrada sem saida"

    period_res = MagicMock()
    daily_calc = _create_daily_time_result(net_worked_seconds=28800.0)
    period_res.daily_results = {curr: daily_calc}
    period_res.daily_waivers = {curr: None}

    h_day = service._build_history_day(
        current=curr,
        today_date=today,
        records=[rec],
        holidays=[holiday],
        anomalies=[anomaly],
        period_result=period_res,
        is_manager=True,
    )
    assert h_day.date == curr
    assert h_day.is_holiday is True
    assert h_day.holiday_name == "Ano Novo"
    assert h_day.status == "Normal"
    assert h_day.worked_time == "08:00"
    assert h_day.has_anomaly is True
    assert h_day.anomalies == ["Entrada sem saida"]
    assert len(h_day.punches) == 1

    abono_obj = MagicMock()
    abono_obj.id = 99
    abono_obj.amount_hours = 4.0
    period_res.daily_waivers = {curr: abono_obj}
    period_res.daily_results = {curr: _create_daily_time_result(net_worked_seconds=0.0)}

    h_day_abono_mgr = service._build_history_day(
        current=curr,
        today_date=today,
        records=[],
        holidays=[],
        anomalies=[],
        period_result=period_res,
        is_manager=True,
    )
    assert h_day_abono_mgr.status == "Abono"
    assert h_day_abono_mgr.abono_hours == 4.0
    assert h_day_abono_mgr.abono_id == 99

    h_day_abono_emp = service._build_history_day(
        current=curr,
        today_date=today,
        records=[],
        holidays=[],
        anomalies=[],
        period_result=period_res,
        is_manager=False,
    )
    assert h_day_abono_emp.status == "Abono"
    assert h_day_abono_emp.abono_hours == 4.0
    assert h_day_abono_emp.abono_id is None


def test_build_history_day_with_adjustments(service):
    from app.shared.enums import AdjustmentStatus, AdjustmentType
    curr = date(2024, 1, 1)
    today = date(2024, 1, 15)
    adj = AdjustmentRequest(
        id=15,
        user_id=1,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        target_date=curr,
        amount_hours=2.0,
        approved_amount_hours=1.5,
        status=AdjustmentStatus.APPROVED,
        reason_text="Excedente detectado"
    )
    period_res = MagicMock()
    period_res.daily_results = {curr: _create_daily_time_result(net_worked_seconds=28800.0)}
    period_res.daily_waivers = {curr: None}

    h_day = service._build_history_day(
        current=curr,
        today_date=today,
        records=[],
        holidays=[],
        anomalies=[],
        period_result=period_res,
        is_manager=True,
        daily_excess_adj=adj,
        day_adjustments=[adj]
    )
    assert len(h_day.adjustments) == 1
    assert h_day.adjustments[0].id == 15
    assert h_day.adjustments[0].adjustment_type == AdjustmentType.DAILY_EXCESS
    assert h_day.adjustments[0].approved_amount_hours == 1.5
    assert h_day.adjustments[0].status == AdjustmentStatus.APPROVED


def test_build_detailed_punches(service):
    editor_user = User(id=9, name="Supervisor")
    rec = TimeRecord(
        id=1,
        record_datetime=datetime(2024, 1, 1, 8, 0, 15),
        record_type=RecordType.ENTRY,
        ip_address="10.0.0.1",
        device_name="Catraca",
        platform="DESKTOP",
        biometric_id=5,
        editor=editor_user,
        edit_justification="Esquecimento",
    )

    res_maintainer = service._build_detailed_punches([rec], is_maintainer=True)
    assert len(res_maintainer) == 1
    assert res_maintainer[0].id == 1
    assert res_maintainer[0].time == "08:00:15"
    assert res_maintainer[0].ip_address == "10.0.0.1"
    assert res_maintainer[0].device_name == "Catraca"
    assert res_maintainer[0].platform == "DESKTOP"
    assert res_maintainer[0].biometric_id == 5
    assert res_maintainer[0].edited_by == "Supervisor"
    assert res_maintainer[0].edit_justification == "Esquecimento"

    res_not_maintainer = service._build_detailed_punches([rec], is_maintainer=False)
    assert res_not_maintainer == []


def test_determine_daily_status_all_branches(service):
    assert service._determine_daily_status(True, True, False, False, 0, 0, False, True) == "Feriado"
    assert service._determine_daily_status(True, False, True, False, 0, 0, False, True) == "Fim de semana"
    assert service._determine_daily_status(True, False, False, False, 0, 0, False, True) == ""

    assert service._determine_daily_status(False, False, False, True, 0, 0, False, True) == "Abono"
    assert service._determine_daily_status(False, True, False, False, 0, 0, False, True) == "Feriado"

    assert service._determine_daily_status(False, False, True, False, 3600, 0, False, True) == "Normal"
    assert service._determine_daily_status(False, False, True, False, 0, 0, False, True) == "Fim de semana"

    assert service._determine_daily_status(False, False, False, False, 0, 28800, True, True) == ""
    assert service._determine_daily_status(False, False, False, False, 0, 28800, False, True) == "Falta"

    assert service._determine_daily_status(False, False, False, False, 0, 0, False, False) == "-"
    assert service._determine_daily_status(False, False, False, False, 28800, 28800, False, True) == "Normal"


def test_build_daily_report_item(service):
    curr = date(2024, 1, 10)
    today = date(2024, 1, 15)

    rec = TimeRecord(
        id=1,
        record_datetime=datetime(2024, 1, 10, 8, 0),
        record_type=RecordType.ENTRY,
    )
    holiday = Holiday(date=curr, name="Feriado Local")

    period_res = MagicMock()
    daily_calc = _create_daily_time_result(
        net_worked_seconds=28800.0,
        unapproved_extra_seconds=1800.0,
        extra_seconds=3600.0,
        missing_seconds=0.0,
        waiver_seconds=7200.0,
        entries=["08:00"],
        exits=["17:00"],
        punches=["08:00", "17:00"],
    )
    period_res.daily_results = {curr: daily_calc}
    period_res.daily_waivers = {curr: MagicMock(id=50)}
    period_res.daily_expected_seconds = {curr: 28800.0}

    item = service._build_daily_report_item(
        current=curr,
        today_date=today,
        all_records=[rec],
        holidays=[holiday],
        period_result=period_res,
        has_schedule=True,
        is_maintainer=True,
    )
    assert item.date == curr
    assert item.is_holiday is True
    assert item.holiday_name == "Feriado Local"
    assert item.adjustment_id == 50
    assert item.worked_hours == 8.0
    assert item.expected_hours == 8.0
    assert item.extra_hours == 1.0
    assert item.missing_hours == 0.0
    assert item.balance_hours == 1.0
    assert item.worked_minutes == 480
    assert item.worked_time == "08:00"
    assert item.expected_time == "08:00"
    assert item.unapproved_extra_time == "00:30"
    assert "Abono: 02:00" in item.punches
    assert item.detailed_punches is not None


@pytest.mark.asyncio
async def test_get_history_report_user_not_found(service, mock_db, mock_repo_user):
    mock_repo_user.get.return_value = None
    curr_user = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(ReportUserNotFoundError) as exc:
        await service.get_history_report(mock_db, user_id=999, month=1, year=2024, current_user=curr_user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_history_report_future_date(service, mock_db):
    curr_user = User(id=1, role=UserRole.EMPLOYEE)
    future_year = datetime.now().year + 2
    res = await service.get_history_report(mock_db, user_id=1, month=1, year=future_year, current_user=curr_user)
    assert res.total_worked_time == "00:00"
    assert res.days == []


@pytest.mark.asyncio
async def test_get_history_report_success(service, mock_db, mock_repo_user, mock_repo_time_record,
                                    mock_repo_holiday, mock_anomaly_service, mock_time_calc_service):
    user = User(id=1, name="Test User", historical_schedules=[])
    mock_repo_user.get.return_value = user
    mock_repo_time_record.get_by_range.return_value = []
    mock_repo_holiday.get_by_month.return_value = []
    mock_anomaly_service.get_anomalies = AsyncMock(return_value=[])

    period_calc = PeriodTimeResult(
        total_net_worked_seconds=57600.0,
        total_gross_worked_seconds=57600.0,
        total_expected_seconds=57600.0,
        total_waiver_seconds=0.0,
        total_unapproved_extra_seconds=0.0,
        total_extra_seconds=0.0,
        total_missing_seconds=0.0,
        final_balance_seconds=0.0,
        daily_results=defaultdict(lambda: _create_daily_time_result(net_worked_seconds=28800.0)),
        daily_expected_seconds=defaultdict(lambda: 28800.0),
        daily_is_holiday=defaultdict(lambda: False),
        daily_waivers=defaultdict(lambda: None),
    )
    mock_time_calc_service.calculate_period_time.return_value = period_calc

    curr_user = User(id=1, role=UserRole.EMPLOYEE)
    res = await service.get_history_report(mock_db, user_id=1, month=None, year=None, current_user=curr_user)
    assert res.month == datetime.now().month
    assert res.year == datetime.now().year
    assert res.total_worked_time == "16:00"
    assert len(res.days) >= 1


@pytest.mark.asyncio
async def test_fetch_report_data_database_queries(service, mock_db, mock_repo_time_record, mock_repo_holiday):
    mock_repo_time_record.get_by_range.return_value = ["rec1"]
    mock_repo_holiday.get_by_month.return_value = ["hol1"]

    rec, adj, hol = await service._fetch_report_data(
        mock_db,
        user_id=1,
        month=1,
        year=2024,
        start_dt=datetime(2024, 1, 1),
        end_dt=datetime(2024, 1, 31),
        prefetched_records=None,
        prefetched_adjustments=None,
        prefetched_holidays=None,
    )
    assert rec == ["rec1"]
    assert hol == ["hol1"]
    assert isinstance(adj, list)


@pytest.mark.asyncio
async def test_fetch_report_data_prefetched(service, mock_db):
    rec, adj, hol = await service._fetch_report_data(
        mock_db,
        user_id=1,
        month=1,
        year=2024,
        start_dt=datetime(2024, 1, 1),
        end_dt=datetime(2024, 1, 31),
        prefetched_records=["r"],
        prefetched_adjustments=["a"],
        prefetched_holidays=["h"],
    )
    assert rec == ["r"]
    assert adj == ["a"]
    assert hol == ["h"]


@pytest.mark.asyncio
async def test_get_advanced_user_report_not_found(service, mock_db, mock_repo_user):
    mock_repo_user.get.return_value = None
    res = await service.get_advanced_user_report(mock_db, user_id=999, month=1, year=2024)
    assert res is None


@pytest.mark.asyncio
async def test_get_advanced_user_report_success(service, mock_db, mock_repo_user, mock_time_calc_service):
    user = User(id=1, name="John Doe", historical_schedules=[])
    mock_repo_user.get.return_value = user

    daily_results = defaultdict(lambda: _create_daily_time_result(net_worked_seconds=28800.0, extra_seconds=3600.0))
    daily_results[date(2024, 1, 3)] = _create_daily_time_result(net_worked_seconds=0.0, extra_seconds=0.0,
                                                                missing_seconds=28800.0)

    period_calc = PeriodTimeResult(
        total_net_worked_seconds=72000.0,
        total_gross_worked_seconds=72000.0,
        total_expected_seconds=86400.0,
        total_waiver_seconds=0.0,
        total_unapproved_extra_seconds=0.0,
        total_extra_seconds=7200.0,
        total_missing_seconds=14400.0,
        final_balance_seconds=-7200.0,
        daily_results=daily_results,
        daily_expected_seconds=defaultdict(lambda: 28800.0),
        daily_is_holiday=defaultdict(lambda: False),
        daily_waivers=defaultdict(lambda: None),
    )
    mock_time_calc_service.calculate_period_time.return_value = period_calc

    curr_user = User(id=1, role=UserRole.MAINTAINER)
    res = await service.get_advanced_user_report(mock_db, user_id=1, month=1, year=2024, current_user=curr_user)
    assert res is not None
    assert res.summary.user_id == 1
    assert res.summary.absences >= 1
    assert res.summary.user_name == "John Doe"
    assert res.summary.total_worked_time == "20:00"
    assert res.summary.total_expected_time == "24:00"
    assert res.summary.total_worked_hours == 20.0
    assert res.summary.total_expected_hours == 24.0
    assert res.summary.total_extra_hours == 2.0
    assert res.summary.total_missing_hours == 4.0
    assert res.summary.final_balance == -2.0
    assert len(res.daily_details) == 31


def test_check_report_permission(service):
    maint = User(id=1, role=UserRole.MAINTAINER)
    service.check_report_permission(maint)

    mgr = User(id=2, role=UserRole.MANAGER)
    service.check_report_permission(mgr)

    emp_allowed = User(id=3, role=UserRole.EMPLOYEE, can_export_report=True)
    service.check_report_permission(emp_allowed)


def test_check_report_permission_forbidden(service):
    emp_forbidden = User(id=4, role=UserRole.EMPLOYEE, can_export_report=False)
    with pytest.raises(ReportGlobalPermissionError) as exc:
        service.check_report_permission(emp_forbidden)
    assert exc.value.status_code == 403


def test_check_user_report_access(service):
    maint = User(id=1, role=UserRole.MAINTAINER)
    service.check_user_report_access(maint, user_id=99)

    mgr = User(id=2, role=UserRole.MANAGER)
    service.check_user_report_access(mgr, user_id=99)

    emp_self = User(id=3, role=UserRole.EMPLOYEE, can_export_report=False)
    service.check_user_report_access(emp_self, user_id=3)

    emp_with_perm = User(id=4, role=UserRole.EMPLOYEE, can_export_report=True)
    service.check_user_report_access(emp_with_perm, user_id=99)


def test_check_user_report_access_forbidden(service):
    emp_forbidden = User(id=5, role=UserRole.EMPLOYEE, can_export_report=False)
    with pytest.raises(ReportAccessDeniedError) as exc:
        service.check_user_report_access(emp_forbidden, user_id=99, detail="Acesso bloqueado.")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Acesso bloqueado."


@pytest.mark.asyncio
async def test_get_advanced_user_report_or_404_success(service, mock_db):
    dummy_rep = MagicMock()
    with patch.object(service, "get_advanced_user_report", new_callable=AsyncMock, return_value=dummy_rep):
        assert await service.get_advanced_user_report_or_404(mock_db, 1, 1, 2024, MagicMock()) == dummy_rep


@pytest.mark.asyncio
async def test_get_advanced_user_report_or_404_not_found(service, mock_db):
    dummy_user = MagicMock()
    with patch.object(service, "get_advanced_user_report", new_callable=AsyncMock, return_value=None):
        with pytest.raises(ReportNotFoundOrIncompleteError) as exc:
            await service.get_advanced_user_report_or_404(mock_db, 1, 1, 2024, dummy_user)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_validate_excel_export_permission_maintainer(service, mock_db):
    maint = MagicMock(spec=User)
    maint.role = UserRole.MAINTAINER
    await service.validate_excel_export_permission(mock_db, maint, 1, 2024, datetime(2024, 2, 1))


@pytest.mark.asyncio
async def test_validate_excel_export_permission_manager_pending_adjustments(service, mock_db):
    mgr = MagicMock(spec=User)
    mgr.role = UserRole.MANAGER
    mock_db.query.side_effect = None
    mock_db.query.return_value.items = [AdjustmentRequest()]
    target_date = datetime(2024, 2, 1)
    with pytest.raises(PendingAdjustmentsExistError) as exc_mgr:
        await service.validate_excel_export_permission(mock_db, mgr, 1, 2024, target_date)
    assert exc_mgr.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_excel_export_permission_manager_no_pending(service, mock_db):
    mgr = MagicMock(spec=User)
    mgr.role = UserRole.MANAGER
    mock_db.query.side_effect = None
    mock_db.query.return_value.items = []
    await service.validate_excel_export_permission(mock_db, mgr, 1, 2024, datetime(2024, 2, 1))


@pytest.mark.asyncio
async def test_validate_excel_export_permission_employee_no_export_perm(service, mock_db):
    emp = MagicMock(spec=User)
    emp.role = UserRole.EMPLOYEE
    emp.can_export_report = False
    target_date = datetime(2024, 2, 1)
    with pytest.raises(ReportExportPermissionError) as exc_emp1:
        await service.validate_excel_export_permission(mock_db, emp, 1, 2024, target_date)
    assert exc_emp1.value.status_code == 403


@pytest.mark.asyncio
async def test_validate_excel_export_permission_employee_wrong_month(service, mock_db):
    emp = MagicMock(spec=User)
    emp.role = UserRole.EMPLOYEE
    emp.can_export_report = True
    now = datetime(2024, 5, 1)
    with pytest.raises(EmployeePreviousMonthOnlyError) as exc_emp2:
        await service.validate_excel_export_permission(mock_db, emp, 1, 2024, now)
    assert exc_emp2.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_excel_export_permission_employee_unclosed_payroll(service, mock_db):
    emp = MagicMock(spec=User)
    emp.role = UserRole.EMPLOYEE
    emp.can_export_report = True
    now = datetime(2024, 5, 1)
    mock_db.query.side_effect = None
    mock_db.query.return_value.items = []
    with pytest.raises(PayrollNotClosedForReportError) as exc_emp3:
        await service.validate_excel_export_permission(mock_db, emp, 4, 2024, now)
    assert exc_emp3.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_excel_export_permission_employee_success(service, mock_db):
    emp = MagicMock(spec=User)
    emp.role = UserRole.EMPLOYEE
    emp.can_export_report = True
    now = datetime(2024, 5, 1)
    mock_db.query.side_effect = None
    mock_db.query.return_value.items = [PayrollClosure(month=4, year=2024, is_closed=True)]
    await service.validate_excel_export_permission(mock_db, emp, 4, 2024, now)

    now_jan = datetime(2024, 1, 15)
    mock_db.query.return_value.items = [PayrollClosure(month=12, year=2023, is_closed=True)]
    await service.validate_excel_export_permission(mock_db, emp, 12, 2023, now_jan)


def test_locale_error_handled():
    with patch("locale.setlocale", side_effect=locale.Error):
        import app.features.reports.report_service
        importlib.reload(app.features.reports.report_service)


def test_determine_excess_info_disabled_or_legacy(service):
    acc_res = MagicMock()
    acc_res.total_excess_seconds = 3600

    # schedule is None
    has_excess, status, adj_id = service._determine_excess_info(acc_res, None, schedule=None)
    assert has_excess is False
    assert status is None
    assert adj_id is None

    # schedule with is_daily_excess_enabled = False
    sch_disabled = MagicMock(is_daily_excess_enabled=False)
    has_excess, status, adj_id = service._determine_excess_info(acc_res, None, schedule=sch_disabled)
    assert has_excess is False
    assert status is None
    assert adj_id is None

    # legacy schedule with is_daily_excess_enabled = None
    sch_legacy = MagicMock(is_daily_excess_enabled=None)
    has_excess, status, adj_id = service._determine_excess_info(acc_res, None, schedule=sch_legacy)
    assert has_excess is False
    assert status is None
    assert adj_id is None


def test_determine_excess_info_enabled(service):
    acc_res = MagicMock()
    acc_res.total_excess_seconds = 3600

    sch_enabled = MagicMock(is_daily_excess_enabled=True)
    has_excess, status, adj_id = service._determine_excess_info(acc_res, None, schedule=sch_enabled)
    assert has_excess is True
    assert status == "PENDING"
    assert adj_id is None

    adj = MagicMock()
    adj.id = 42
    adj.status = AdjustmentStatus.APPROVED
    has_excess, status, adj_id = service._determine_excess_info(acc_res, adj, schedule=sch_enabled)
    assert has_excess is True
    assert status == AdjustmentStatus.APPROVED.value
    assert adj_id == 42
