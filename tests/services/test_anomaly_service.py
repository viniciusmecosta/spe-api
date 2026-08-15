from datetime import date, datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException

import pytest
from app.domain.enums import RecordType, AdjustmentType, AdjustmentStatus, UserRole
from app.features.timesheets.anomaly_service import anomaly_service


class MockUser:
    def __init__(self, id, is_active=True, role=UserRole.EMPLOYEE, name="Test User", historical_schedules=None):
        self.id = id
        self.is_active = is_active
        self.role = role
        self.name = name
        self.historical_schedules = historical_schedules or []


class MockSchedule:
    def __init__(self, valid_from, valid_until, day_of_week, entry_1):
        self.valid_from = valid_from
        self.valid_until = valid_until
        self.day_of_week = day_of_week
        self.entry_1 = entry_1


class MockTimeRecord:
    def __init__(self, user_id, record_datetime, record_type):
        self.user_id = user_id
        self.record_datetime = record_datetime
        self.record_type = record_type


class MockAdjustmentRequest:
    def __init__(self, user_id, target_date, adjustment_type, status, amount_hours, time=None):
        self.user_id = user_id
        self.target_date = target_date
        self.adjustment_type = adjustment_type
        self.status = status
        self.amount_hours = amount_hours
        self.time = time


def test_format_duration():
    assert anomaly_service._format_duration(3600) == "1h00"
    assert anomaly_service._format_duration(3660) == "1h01"
    assert anomaly_service._format_duration(0) == "0h00"


def test_check_missing_entries_exits():
    current_date = date.today() - timedelta(days=1)
    
    records = [
        MockTimeRecord(1, datetime.combine(current_date, datetime.min.time()), RecordType.EXIT)
    ]
    anomalies = anomaly_service._check_missing_entries_exits(1, "Test", current_date, records)
    assert len(anomalies) == 1
    assert anomalies[0].type == "MISSING_ENTRY"

    records = [
        MockTimeRecord(1, datetime.combine(current_date, datetime.min.time()), RecordType.ENTRY)
    ]
    anomalies = anomaly_service._check_missing_entries_exits(1, "Test", current_date, records)
    assert len(anomalies) == 1
    assert anomalies[0].type == "MISSING_EXIT"

    anomalies = anomaly_service._check_missing_entries_exits(1, "Test", date.today(), records)
    assert len(anomalies) == 0


def test_check_consecutive_records():
    current_date = date.today()
    records = [
        MockTimeRecord(1, datetime.now(), RecordType.ENTRY),
        MockTimeRecord(1, datetime.now(), RecordType.ENTRY)
    ]
    anomalies = anomaly_service._check_consecutive_records(1, "Test", current_date, records)
    assert len(anomalies) == 1
    assert anomalies[0].type == "DOUBLE_ENTRY"

    records = [
        MockTimeRecord(1, datetime.now(), RecordType.EXIT),
        MockTimeRecord(1, datetime.now(), RecordType.EXIT)
    ]
    anomalies = anomaly_service._check_consecutive_records(1, "Test", current_date, records)
    assert len(anomalies) == 1
    assert anomalies[0].type == "DOUBLE_EXIT"


def test_check_long_intervals():
    current_date = date.today()
    records = [
        MockTimeRecord(1, datetime(2023, 1, 1, 8, 0), RecordType.ENTRY),
        MockTimeRecord(1, datetime(2023, 1, 1, 17, 0), RecordType.EXIT)
    ]
    anomalies = anomaly_service._check_long_intervals(1, "Test", current_date, records)
    assert len(anomalies) == 1
    assert anomalies[0].type == "LONG_INTERVAL"

    records = [
        MockTimeRecord(1, datetime(2023, 1, 1, 8, 0), RecordType.ENTRY),
        MockTimeRecord(1, datetime(2023, 1, 1, 12, 0), RecordType.EXIT)
    ]
    anomalies = anomaly_service._check_long_intervals(1, "Test", current_date, records)
    assert len(anomalies) == 0


def test_check_unapproved_adjustments():
    current_date = date.today()
    
    adj1 = MockAdjustmentRequest(1, current_date, AdjustmentType.EXTRA_TIME, AdjustmentStatus.PENDING, 2.5, datetime(2023, 1, 1, 18, 0).time())
    anomalies1 = anomaly_service._check_unapproved_adjustments(1, "Test", current_date, [adj1], None)
    assert len(anomalies1) == 1
    assert anomalies1[0].type == "UNAPPROVED_EXTRA_TIME"
    assert "150 minutos extras pendentes de aprovação" in anomalies1[0].description
    assert "horário de entrada definido: 18:00" in anomalies1[0].description
    
    adj2 = MockAdjustmentRequest(1, current_date, AdjustmentType.EXTRA_TIME, AdjustmentStatus.PENDING, None)
    anomalies2 = anomaly_service._check_unapproved_adjustments(1, "Test", current_date, [adj2], datetime(2023, 1, 1, 9, 0).time())
    assert len(anomalies2) == 1
    assert "0 minutos extras pendentes de aprovação" in anomalies2[0].description
    
    adj_pending_no_time = MockAdjustmentRequest(1, current_date, AdjustmentType.EXTRA_TIME, AdjustmentStatus.PENDING, 1.0, None)
    anomalies_pending_no_time = anomaly_service._check_unapproved_adjustments(1, "Test", current_date, [adj_pending_no_time], None)
    assert len(anomalies_pending_no_time) == 1
    assert anomalies_pending_no_time[0].description == "60 minutos extras pendentes de aprovação"
    
    adj3 = MockAdjustmentRequest(1, current_date, AdjustmentType.EXTRA_TIME, AdjustmentStatus.APPROVED, 1.0)
    anomalies3 = anomaly_service._check_unapproved_adjustments(1, "Test", current_date, [adj3], None)
    assert len(anomalies3) == 0
    
    adj4 = MockAdjustmentRequest(1, current_date, AdjustmentType.EXTRA_TIME, AdjustmentStatus.REJECTED, 1.5, datetime(2023, 1, 1, 19, 0).time())
    anomalies4 = anomaly_service._check_unapproved_adjustments(1, "Test", current_date, [adj4], None)
    assert len(anomalies4) == 1
    assert anomalies4[0].type == "UNAPPROVED_EXTRA_TIME"
    assert "Hora extra negada: 90 minutos não aprovados" in anomalies4[0].description
    assert "horário de entrada: 19:00" in anomalies4[0].description
    
    adj5 = MockAdjustmentRequest(1, current_date, AdjustmentType.EXTRA_TIME, AdjustmentStatus.REJECTED, 1.0)
    anomalies5 = anomaly_service._check_unapproved_adjustments(1, "Test", current_date, [adj5], None)
    assert len(anomalies5) == 1
    assert anomalies5[0].type == "UNAPPROVED_EXTRA_TIME"
    assert anomalies5[0].description == "Hora extra negada: 60 minutos não aprovados"


def test_check_day_anomalies():
    current_date = date.today()
    records = [
        MockTimeRecord(1, datetime(2023, 1, 1, 8, 0), RecordType.ENTRY),
        MockTimeRecord(1, datetime(2023, 1, 1, 20, 0), RecordType.EXIT)
    ]
    anomalies = anomaly_service._check_day_anomalies(1, "Test", current_date, records)
    assert any(a.type == "EXCESSIVE_HOURS" for a in anomalies)
    
    anomalies_ignored = anomaly_service._check_day_anomalies(1, "Test", current_date, records, ignore_excessive_hours=True)
    assert not any(a.type == "EXCESSIVE_HOURS" for a in anomalies_ignored)


def test_get_expected_entry_time():
    schedule1 = MockSchedule(date(2023, 1, 1), date(2023, 1, 31), 0, datetime(2023, 1, 1, 9, 0).time())
    user = MockUser(1, historical_schedules=[schedule1])
    
    entry_time = anomaly_service._get_expected_entry_time(user, date(2023, 1, 2))
    assert entry_time == datetime(2023, 1, 1, 9, 0).time()
    
    entry_time_none = anomaly_service._get_expected_entry_time(user, date(2023, 1, 3))
    assert entry_time_none is None
    
    entry_time_no_user = anomaly_service._get_expected_entry_time(None, date(2023, 1, 2))
    assert entry_time_no_user is None


@patch("app.features.timesheets.anomaly_service.user_repository")
@patch("app.features.timesheets.anomaly_service.time_record_repository")
def test_get_anomalies_with_user(mock_tr_repo, mock_user_repo, db_session_mock):
    mock_user_repo.get.return_value = MockUser(1)
    mock_tr_repo.get_by_users_and_range.return_value = [
        MockTimeRecord(1, datetime(2023, 1, 1, 8, 0), RecordType.ENTRY),
        MockTimeRecord(1, datetime(2023, 1, 1, 17, 0), RecordType.EXIT)
    ]
    adj = MockAdjustmentRequest(1, date(2023, 1, 1), AdjustmentType.EXTRA_TIME, AdjustmentStatus.PENDING, 2.5, datetime(2023, 1, 1, 18, 0).time())
    db_session_mock.query.return_value.items = [adj]
    
    anomalies = anomaly_service.get_anomalies(db_session_mock, date(2023, 1, 1), date(2023, 1, 31), user_id=1)
    assert len(anomalies) == 2
    types = [a.type for a in anomalies]
    assert "LONG_INTERVAL" in types
    assert "UNAPPROVED_EXTRA_TIME" in types


@patch("app.features.timesheets.anomaly_service.user_repository")
@patch("app.features.timesheets.anomaly_service.time_record_repository")
def test_get_anomalies_no_target_users(mock_tr_repo, mock_user_repo, db_session_mock):
    mock_user_repo.get_active_employees.return_value = []
    
    anomalies = anomaly_service.get_anomalies(db_session_mock, date(2023, 1, 1), date(2023, 1, 31))
    assert len(anomalies) == 0


def test_get_anomalies_by_month_invalid(db_session_mock):
    with pytest.raises(HTTPException) as exc_info:
        anomaly_service.get_anomalies_by_month(db_session_mock, 13, 2023)
    assert exc_info.value.status_code == 400


@patch.object(anomaly_service, "get_anomalies")
def test_get_anomalies_by_month_valid(mock_get_anomalies, db_session_mock):
    mock_get_anomalies.return_value = []
    
    result = anomaly_service.get_anomalies_by_month(db_session_mock, 1, 2023)
    assert result == []
    mock_get_anomalies.assert_called_once()
    
    result = anomaly_service.get_anomalies_by_month(db_session_mock, 1, 2099)
    assert result == []
