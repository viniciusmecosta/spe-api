import pytest
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock
from sqlalchemy.exc import SQLAlchemyError

from app.services.tolerance_cron_service import ToleranceCronService
from app.domain.models.enums import AdjustmentStatus, AdjustmentType, RecordType
from app.domain.models.adjustment import AdjustmentRequest

def make_query_mock(items):
    qm = MagicMock()
    qm.filter.return_value = qm
    qm.order_by.return_value = qm
    qm.first.return_value = items[0] if items else None
    qm.all.return_value = items
    return qm

@pytest.fixture
def base_record():
    record = MagicMock()
    record.id = 1
    record.user_id = 1
    record.user.is_tolerance_exempt = False
    record.record_datetime = datetime(2026, 7, 24, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    record.is_verified = False
    record.record_type = RecordType.ENTRY
    return record

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.entry_1 = time(8, 0)
    return config

@pytest.fixture
def tolerance_service():
    return ToleranceCronService()

def test_process_entry_record_exempt(tolerance_service, db_session_mock, base_record):
    base_record.user.is_tolerance_exempt = True
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True

def test_process_entry_record_no_config(tolerance_service, db_session_mock, base_record):
    db_session_mock.query.return_value = make_query_mock([])
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True

def test_process_entry_record_no_entry_1(tolerance_service, db_session_mock, base_record, mock_config):
    mock_config.entry_1 = None
    db_session_mock.query.return_value = make_query_mock([mock_config])
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True

def test_process_entry_record_not_first_entry(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([MagicMock(id=2)])
    ]
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(), ZoneInfo("America/Sao_Paulo"))
    assert base_record.is_verified is True

def test_process_entry_record_diff_less_than_5(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 56, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, datetime.now(tz), tz)
    assert base_record.is_verified is True

def test_process_entry_record_diff_greater_than_5_now_less(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 50, tzinfo=tz)
    now = datetime(2026, 7, 24, 7, 55, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, now, tz)
    assert base_record.is_verified is False

def test_process_entry_record_diff_greater_than_5_existing_adj(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([]),
        make_query_mock([MagicMock()])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 50, tzinfo=tz)
    now = datetime(2026, 7, 24, 8, 10, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, now, tz)
    assert base_record.is_verified is True
    db_session_mock.add.assert_not_called()

def test_process_entry_record_diff_greater_than_5_no_adj(tolerance_service, db_session_mock, base_record, mock_config):
    db_session_mock.query.side_effect = [
        make_query_mock([mock_config]),
        make_query_mock([]),
        make_query_mock([])
    ]
    tz = ZoneInfo("America/Sao_Paulo")
    base_record.record_datetime = datetime(2026, 7, 24, 7, 50, tzinfo=tz)
    base_record.record_datetime = base_record.record_datetime.replace(tzinfo=None)
    now = datetime(2026, 7, 24, 8, 10, tzinfo=tz)
    tolerance_service._process_entry_record(db_session_mock, base_record, now, tz)
    assert base_record.is_verified is True
    db_session_mock.add.assert_called_once()
    added = db_session_mock.add.call_args[0][0]
    assert added.adjustment_type == AdjustmentType.EXTRA_TIME

def test_process_unverified_entries_success(tolerance_service, db_session_mock, base_record, mocker):
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    mocker.patch("app.services.tolerance_cron_service.get_db_session", return_value=ContextManagerMock())
    db_session_mock.query.return_value = make_query_mock([base_record])
    mocker.patch.object(tolerance_service, "_process_entry_record")
    tolerance_service.process_unverified_entries()
    tolerance_service._process_entry_record.assert_called_once()
    db_session_mock.commit.assert_called_once()

def test_process_unverified_entries_sqlalchemy_error(tolerance_service, db_session_mock, mocker):
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    mocker.patch("app.services.tolerance_cron_service.get_db_session", return_value=ContextManagerMock())
    db_session_mock.query.side_effect = SQLAlchemyError("DB Error")
    mock_logger = mocker.patch("app.services.tolerance_cron_service.logger")
    tolerance_service.process_unverified_entries()
    mock_logger.exception.assert_called_once()

def test_process_unverified_entries_exception(tolerance_service, db_session_mock, mocker):
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    mocker.patch("app.services.tolerance_cron_service.get_db_session", return_value=ContextManagerMock())
    db_session_mock.query.side_effect = Exception("General Error")
    mock_logger = mocker.patch("app.services.tolerance_cron_service.logger")
    tolerance_service.process_unverified_entries()
    mock_logger.exception.assert_called_once()

def test_reprocess_historical_entries(tolerance_service, db_session_mock, base_record, mocker):
    db_session_mock.query.return_value = make_query_mock([base_record])
    mocker.patch.object(tolerance_service, "_process_entry_record")
    start_date = date(2026, 7, 1)
    end_date = date(2026, 7, 31)
    user_ids = [1]
    tolerance_service.reprocess_historical_entries(db_session_mock, start_date, end_date, user_ids)
    tolerance_service._process_entry_record.assert_called_once()
    db_session_mock.commit.assert_called_once()
