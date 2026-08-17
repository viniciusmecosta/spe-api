from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.features.reports.dashboard_service import dashboard_service
from app.features.reports.report_schemas import DashboardMetricsResponse, TeamHoursResponse
from app.features.users.user_models import User
from app.shared.enums import RecordType


@pytest.fixture
def mock_db_query(db_session_mock):
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_options = MagicMock()

    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_query.options.return_value = mock_options
    mock_options.filter.return_value = mock_filter

    return {
        "query": mock_query,
        "filter": mock_filter,
        "options": mock_options
    }


@patch("app.features.reports.dashboard_service.time_record_repository.count_unique_users_in_range")
@patch("app.features.reports.dashboard_service.adjustment_repository.count_pending")
@patch("app.features.reports.dashboard_service.datetime")
def test_get_dashboard_metrics(mock_datetime, mock_count_pending, mock_count_users, db_session_mock, mock_db_query):
    mock_db_query["filter"].count.return_value = 5
    mock_count_pending.return_value = 3
    mock_count_users.return_value = 2

    fixed_now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    mock_datetime.now.return_value = fixed_now
    mock_datetime.combine = datetime.combine
    mock_datetime.min = datetime.min
    mock_datetime.max = datetime.max

    response = dashboard_service.get_dashboard_metrics(db_session_mock)

    assert isinstance(response, DashboardMetricsResponse)
    assert response.total_active_employees == 5
    assert response.pending_adjustments == 3
    assert response.employees_present_today == 2


@patch("app.features.reports.dashboard_service.anomaly_service.get_anomalies")
@patch("app.features.reports.dashboard_service.time_record_repository.get_by_range")
@patch("app.features.reports.dashboard_service.date")
@patch("app.features.reports.dashboard_service.trusted_time_service.get_trusted_time")
@patch("app.features.reports.dashboard_service.datetime")
def test_get_my_dashboard_with_records(mock_datetime, mock_get_trusted_time, mock_date, mock_get_by_range,
                                       mock_get_anomalies, db_session_mock, mock_db_query):
    user = User(id=1, name="Test User")

    fixed_now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    mock_datetime.now.return_value = fixed_now
    mock_datetime.combine = datetime.combine
    mock_datetime.min = datetime.min
    mock_datetime.max = datetime.max
    mock_date.side_effect = date
    mock_get_trusted_time.return_value = (fixed_now, True)

    record1 = MagicMock()
    record1.id = 1
    record1.short_id = "short1"
    record1.record_datetime = datetime(2026, 7, 15, 8, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    record1.record_type = RecordType.ENTRY

    record2 = MagicMock()
    record2.id = 2
    record2.short_id = "short2"
    record2.record_datetime = datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    record2.record_type = RecordType.EXIT

    mock_get_by_range.return_value = [record2, record1]

    anomaly = MagicMock()
    anomaly.date = date(2026, 7, 10)
    anomaly.description = "Test Anomaly"
    mock_get_anomalies.return_value = [anomaly]

    bday_user1 = MagicMock()
    bday_user1.name = "Bday User 1"
    bday_user1.data_nascimento = date(1990, 7, 20)

    bday_user2 = MagicMock()
    bday_user2.name = "Bday User 2"
    bday_user2.data_nascimento = date(1990, 7, 10)

    mock_db_query["filter"].all.return_value = [bday_user1, bday_user2]

    response = dashboard_service.get_my_dashboard(db_session_mock, user)

    assert response.full_name == "Test User"
    assert response.next_punch_type == "ENTRY"
    assert len(response.today_punches) == 2
    assert response.today_punches[0].time == "08:00"
    assert response.today_punches[1].time == "12:00"
    assert len(response.month_anomalies) == 1
    assert response.month_anomalies[0].date == "10/07/2026"
    assert len(response.aniversariantes_do_mes) == 2
    assert response.aniversariantes_do_mes[0].nome == "Bday User 2"
    assert response.aniversariantes_do_mes[0].dia == 10
    assert response.aniversariantes_do_mes[1].nome == "Bday User 1"
    assert response.aniversariantes_do_mes[1].dia == 20


@patch("app.features.reports.dashboard_service.anomaly_service.get_anomalies")
@patch("app.features.reports.dashboard_service.time_record_repository.get_by_range")
@patch("app.features.reports.dashboard_service.date")
@patch("app.features.reports.dashboard_service.trusted_time_service.get_trusted_time")
@patch("app.features.reports.dashboard_service.datetime")
def test_get_my_dashboard_no_records_and_no_bday(mock_datetime, mock_get_trusted_time, mock_date, mock_get_by_range,
                                                 mock_get_anomalies, db_session_mock, mock_db_query):
    user = User(id=1, name="Test User")

    fixed_now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    mock_datetime.now.return_value = fixed_now
    mock_datetime.combine = datetime.combine
    mock_datetime.min = datetime.min
    mock_datetime.max = datetime.max
    mock_date.side_effect = date
    mock_get_trusted_time.return_value = (fixed_now, True)

    mock_get_by_range.return_value = []
    mock_get_anomalies.return_value = []

    bday_user = MagicMock()
    bday_user.name = "No Bday User"
    bday_user.data_nascimento = None
    mock_db_query["filter"].all.return_value = [bday_user]

    response = dashboard_service.get_my_dashboard(db_session_mock, user)

    assert response.next_punch_type == "ENTRY"
    assert len(response.today_punches) == 0
    assert len(response.aniversariantes_do_mes) == 0


@patch("app.features.reports.dashboard_service.time_record_repository.get_by_range")
@patch("app.features.reports.dashboard_service.date")
@patch("app.features.reports.dashboard_service.trusted_time_service.get_trusted_time")
@patch("app.features.reports.dashboard_service.datetime")
def test_get_my_dashboard_start_of_month(mock_datetime, mock_get_trusted_time, mock_date, mock_get_by_range,
                                         db_session_mock, mock_db_query):
    user = User(id=1, name="Test User")

    fixed_now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    mock_datetime.now.return_value = fixed_now
    mock_datetime.combine = datetime.combine
    mock_datetime.min = datetime.min
    mock_datetime.max = datetime.max
    mock_date.side_effect = date
    mock_get_trusted_time.return_value = (fixed_now, True)

    mock_get_by_range.return_value = []
    mock_db_query["filter"].all.return_value = []

    response = dashboard_service.get_my_dashboard(db_session_mock, user)

    assert len(response.month_anomalies) == 0


@patch("app.features.reports.dashboard_service.anomaly_service.get_anomalies")
@patch("app.features.reports.dashboard_service.time_record_repository.get_by_range")
@patch("app.features.reports.dashboard_service.date")
@patch("app.features.reports.dashboard_service.trusted_time_service.get_trusted_time")
@patch("app.features.reports.dashboard_service.datetime")
def test_get_my_dashboard_last_record_entry(mock_datetime, mock_get_trusted_time, mock_date, mock_get_by_range,
                                            mock_get_anomalies, db_session_mock, mock_db_query):
    user = User(id=1, name="Test User")

    fixed_now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    mock_datetime.now.return_value = fixed_now
    mock_datetime.combine = datetime.combine
    mock_datetime.min = datetime.min
    mock_datetime.max = datetime.max
    mock_date.side_effect = date
    mock_get_trusted_time.return_value = (fixed_now, True)

    record1 = MagicMock()
    record1.id = 1
    record1.short_id = "short1"
    record1.record_datetime = datetime(2026, 7, 15, 8, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    record1.record_type = RecordType.ENTRY

    mock_get_by_range.return_value = [record1]
    mock_get_anomalies.return_value = []
    mock_db_query["filter"].all.return_value = []

    response = dashboard_service.get_my_dashboard(db_session_mock, user)

    assert response.next_punch_type == "EXIT"


@patch("app.features.reports.dashboard_service.report_service.get_advanced_user_report")
def test_get_team_worked_hours(mock_get_report, db_session_mock, mock_db_query):
    current_user = User(id=1, name="Admin")

    user1 = MagicMock()
    user1.id = 2
    user1.name = "User 1"

    user2 = MagicMock()
    user2.id = 3
    user2.name = "User 2"

    mock_db_query["filter"].all.return_value = [user1, user2]

    report1 = MagicMock()
    report1.summary.total_worked_minutes = 150

    report2 = MagicMock()
    report2.summary.total_worked_minutes = 45

    mock_get_report.side_effect = [report1, report2]

    response = dashboard_service.get_team_worked_hours(db_session_mock, 7, 2026, current_user)

    assert response.month == 7
    assert response.year == 2026
    assert response.team_total_hours == 2.0
    assert response.team_formatted_time == "2h"
    assert len(response.employees) == 1
    assert response.employees[0].user_id == 2
    assert response.employees[0].short_name == "User 1"
    assert response.employees[0].total_hours == 2.0
    assert response.employees[0].formatted_time == "2h"


@patch("app.features.reports.dashboard_service.report_service.get_advanced_user_report")
def test_get_team_worked_hours_no_report(mock_get_report, db_session_mock, mock_db_query):
    current_user = User(id=1, name="Admin")

    user1 = MagicMock()
    user1.id = 2
    user1.name = "User 1"

    mock_db_query["filter"].all.return_value = [user1]

    mock_get_report.return_value = None

    response = dashboard_service.get_team_worked_hours(db_session_mock, 7, 2026, current_user)

    assert response.team_total_hours == 0.0
    assert response.team_formatted_time == "0h"
    assert len(response.employees) == 0


@patch("app.features.reports.dashboard_service.time_record_repository.count_records_in_range")
@patch("app.features.reports.dashboard_service.adjustment_repository.count_pending")
@patch("app.features.reports.dashboard_service.anomaly_service.get_anomalies_by_month")
@patch("app.features.reports.dashboard_service.time_record_repository.get_by_range")
@patch("app.features.reports.dashboard_service.dashboard_service.get_team_worked_hours")
@patch("app.features.reports.dashboard_service.datetime")
def test_get_manager_dashboard_with_entry(mock_datetime, mock_team_hours, mock_get_by_range, mock_anomalies,
                                          mock_pending, mock_count_punches, db_session_mock):
    user = User(id=1, name="Manager User")
    fixed_now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    mock_datetime.now.return_value = fixed_now
    mock_datetime.combine = datetime.combine
    mock_datetime.min = datetime.min
    mock_datetime.max = datetime.max

    rec1 = MagicMock()
    rec1.id = 10
    rec1.short_id = "short10"
    rec1.record_datetime = datetime(2026, 7, 15, 8, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    rec1.record_type = RecordType.ENTRY

    mock_get_by_range.return_value = [rec1]
    mock_anomalies.return_value = [MagicMock()]
    mock_pending.return_value = 4
    mock_count_punches.return_value = 12
    mock_team_hours.return_value = TeamHoursResponse(month=7, year=2026, team_total_hours=0.0, team_formatted_time="0h",
                                                     employees=[])

    response = dashboard_service.get_manager_dashboard(db_session_mock, user)

    assert response.full_name == "Manager User"
    assert response.next_punch_type == "EXIT"
    assert len(response.today_punches) == 1
    assert response.today_punches[0].id == 10
    assert response.today_punches[0].time == "08:00"
    assert response.total_system_anomalies == 1
    assert response.total_pending_adjustments == 4
    assert response.today_total_punches == 12


@patch("app.features.reports.dashboard_service.time_record_repository.count_records_in_range")
@patch("app.features.reports.dashboard_service.adjustment_repository.count_pending")
@patch("app.features.reports.dashboard_service.anomaly_service.get_anomalies_by_month")
@patch("app.features.reports.dashboard_service.time_record_repository.get_by_range")
@patch("app.features.reports.dashboard_service.dashboard_service.get_team_worked_hours")
@patch("app.features.reports.dashboard_service.datetime")
def test_get_manager_dashboard_empty_records(mock_datetime, mock_team_hours, mock_get_by_range, mock_anomalies,
                                             mock_pending, mock_count_punches, db_session_mock):
    user = User(id=1, name="Manager User")
    fixed_now = datetime(2026, 7, 15, 10, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    mock_datetime.now.return_value = fixed_now
    mock_datetime.combine = datetime.combine
    mock_datetime.min = datetime.min
    mock_datetime.max = datetime.max

    mock_get_by_range.return_value = []
    mock_anomalies.return_value = []
    mock_pending.return_value = 0
    mock_count_punches.return_value = 0
    mock_team_hours.return_value = TeamHoursResponse(month=7, year=2026, team_total_hours=0.0, team_formatted_time="0h",
                                                     employees=[])

    response = dashboard_service.get_manager_dashboard(db_session_mock, user)

    assert response.next_punch_type == "ENTRY"
    assert len(response.today_punches) == 0
