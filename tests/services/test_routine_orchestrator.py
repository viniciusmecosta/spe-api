from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from app.core.config import settings
from app.domain.models.enums import UserRole
from app.domain.models.routine_log import RoutineLog
from app.domain.models.user import User
from app.services.routine_orchestrator import RoutineOrchestrator
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture(autouse=True)
def mock_environment():
    with patch("app.services.routine_orchestrator.settings.ENVIRONMENT", "prod"):
        yield


@pytest.fixture
def mock_get_db_session(db_session_mock):
    with patch("app.services.routine_orchestrator.get_db_session") as m:
        class ContextManagerMock:
            def __enter__(self):
                return db_session_mock
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        m.return_value = ContextManagerMock()
        yield m

@pytest.fixture
def orchestrator():
    return RoutineOrchestrator()

@pytest.fixture
def mock_datetime():
    with patch("app.services.routine_orchestrator.datetime") as dt_mock:
        dt_mock.now.return_value = datetime(2023, 10, 15, 12, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
        yield dt_mock

@pytest.fixture
def mock_backup_service():
    with patch("app.services.routine_orchestrator.backup_service") as m:
        yield m

@pytest.fixture
def mock_telegram_service():
    with patch("app.services.routine_orchestrator.telegram_service") as m:
        yield m

@pytest.fixture
def mock_email_service():
    with patch("app.services.routine_orchestrator.email_service") as m:
        yield m

@pytest.fixture
def mock_daily_report_service():
    with patch("app.services.routine_orchestrator.daily_report_service") as m:
        yield m

@pytest.fixture
def mock_os():
    with patch("app.services.routine_orchestrator.os.path.exists", return_value=True) as m1, \
         patch("app.services.routine_orchestrator.os.remove") as m2:
        yield m1, m2

@pytest.fixture
def mock_get_log_path():
    with patch("app.services.routine_orchestrator.get_log_path", return_value="/tmp/test.log") as m:
        yield m


def test_execute_hourly_backup_telegram_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 14), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        orchestrator.execute_hourly_backup_telegram()

def test_execute_hourly_backup_telegram_already_exists(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        db_session_mock.query.return_value.items = [RoutineLog(routine_type="TELEGRAM_HOURLY_BACKUP", status="SUCCESS")]
        orchestrator.execute_hourly_backup_telegram()

def test_execute_hourly_backup_telegram_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        db_session_mock.query.side_effect = SQLAlchemyError("DB Error")
        orchestrator.execute_hourly_backup_telegram()

def test_execute_hourly_backup_telegram_backup_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        db_session_mock.query.return_value.items = []
        mock_backup_service.create_safe_backup.return_value = None
        orchestrator.execute_hourly_backup_telegram()

def test_execute_hourly_backup_telegram_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_telegram_service, mock_os):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        db_session_mock.query.return_value.items = []
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_telegram_service.send_document.return_value = True
        orchestrator.execute_hourly_backup_telegram()
        db_session_mock.add.assert_called_once()
        mock_os[1].assert_any_call("/tmp/backup.zip")

def test_execute_hourly_backup_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_telegram_service, mock_os):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        db_session_mock.query.return_value.items = []
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_telegram_service.send_document.return_value = False
        orchestrator.execute_hourly_backup_telegram()
        db_session_mock.add.assert_not_called()

def test_execute_hourly_backup_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_telegram_service, mock_os):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        db_session_mock.query.return_value.items = []
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_telegram_service.send_document.return_value = True
        db_session_mock.add.side_effect = SQLAlchemyError("DB Error")
        orchestrator.execute_hourly_backup_telegram()

def test_send_managerial_report_telegram_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 14):
        orchestrator.send_managerial_report_telegram()

def test_send_managerial_report_telegram_already_ran(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        db_session_mock.query.return_value.items = [RoutineLog(routine_type="TELEGRAM_DAILY_REPORT", status="SUCCESS")]
        orchestrator.send_managerial_report_telegram()

def test_send_managerial_report_telegram_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        db_session_mock.query.side_effect = SQLAlchemyError("DB Error")
        orchestrator.send_managerial_report_telegram()

def test_send_managerial_report_telegram_success_with_previous(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_telegram_service, mock_get_log_path, mock_os):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    if self.n == 1:
                        return None
                    return RoutineLog(target_date=datetime(2023, 10, 13).date())
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        mock_telegram_service.generate_report_text.return_value = "Report"
        mock_telegram_service.send_text.return_value = True
        orchestrator.send_managerial_report_telegram()
        db_session_mock.add.assert_called_once()
        mock_telegram_service.send_document.assert_called()

def test_send_managerial_report_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_telegram_service, mock_get_log_path, mock_os):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    return None
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        mock_telegram_service.generate_report_text.return_value = "Report"
        mock_telegram_service.send_text.return_value = False
        orchestrator.send_managerial_report_telegram()
        db_session_mock.add.assert_called_once()

def test_send_managerial_report_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_telegram_service, mock_get_log_path, mock_os):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    return None
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        mock_telegram_service.generate_report_text.return_value = "Report"
        mock_telegram_service.send_text.return_value = True
        db_session_mock.add.side_effect = SQLAlchemyError("DB Error")
        orchestrator.send_managerial_report_telegram()

def test_generate_daily_backup_report(orchestrator, db_session_mock, mock_daily_report_service, mock_get_log_path, mock_os):
    mock_daily_report_service.generate_daily_report_html.return_value = "<p>Report</p>"
    html, att, p_text = orchestrator._generate_daily_backup_report(
        db_session_mock,
        datetime(2023, 10, 13).date(),
        datetime(2023, 10, 14).date()
    )
    assert "<p>Report</p>" in html
    assert len(att) == 2

def test_generate_daily_backup_report_empty(orchestrator, db_session_mock, mock_daily_report_service, mock_get_log_path):
    with patch("app.services.routine_orchestrator.os.path.exists", return_value=False):
        mock_daily_report_service.generate_daily_report_html.return_value = ""
        html, att, p_text = orchestrator._generate_daily_backup_report(
            db_session_mock,
            datetime(2023, 10, 14).date(),
            datetime(2023, 10, 14).date()
        )
        assert "Nenhum período" in html
        assert len(att) == 0

def test_run_daily_backup_routine_email_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 14):
        orchestrator.run_daily_backup_routine_email()

def test_run_daily_backup_routine_email_already_ran(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        db_session_mock.query.return_value.items = [RoutineLog(routine_type="EMAIL_DAILY_BACKUP", status="SUCCESS")]
        orchestrator.run_daily_backup_routine_email()

def test_run_daily_backup_routine_email_no_maintainers(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    return None
                def all(self):
                    return []
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        orchestrator.run_daily_backup_routine_email()

def test_run_daily_backup_routine_email_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        db_session_mock.query.side_effect = SQLAlchemyError("DB Error")
        orchestrator.run_daily_backup_routine_email()

def test_run_daily_backup_routine_email_backup_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    if self.n == 1:
                        return None
                    return RoutineLog(target_date=datetime(2023, 10, 13).date())
                def all(self):
                    return [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        mock_backup_service.create_safe_backup.return_value = None
        orchestrator.run_daily_backup_routine_email()

def test_run_daily_backup_routine_email_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_email_service, mock_daily_report_service, mock_os, mock_get_log_path):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    return None
                def all(self):
                    return [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = True
        orchestrator.run_daily_backup_routine_email()
        db_session_mock.add.assert_called_once()
        mock_os[1].assert_any_call("/tmp/backup.zip")

def test_run_daily_backup_routine_email_send_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_email_service, mock_daily_report_service, mock_os, mock_get_log_path):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    return None
                def all(self):
                    return [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = False
        orchestrator.run_daily_backup_routine_email()
        db_session_mock.add.assert_called_once()

def test_run_daily_backup_routine_email_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_email_service, mock_daily_report_service, mock_os, mock_get_log_path):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        def side_effect_query(*args, **kwargs):
            class MockQuery:
                def __init__(self, n):
                    self.n = n
                def filter(self, *a, **k):
                    return self
                def order_by(self, *a, **k):
                    return self
                def first(self):
                    return None
                def all(self):
                    return [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
            return MockQuery(db_session_mock.query.call_count)
        db_session_mock.query.side_effect = side_effect_query
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = True
        db_session_mock.add.side_effect = SQLAlchemyError("DB Error")
        orchestrator.run_daily_backup_routine_email()

def test_clean_old_logs_already_ran(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    db_session_mock.query.return_value.items = [RoutineLog(routine_type="CLEANUP_ROUTINE_LOGS", status="SUCCESS")]
    orchestrator.clean_old_logs(days_to_keep=30)

def test_clean_old_logs_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    db_session_mock.query.side_effect = SQLAlchemyError("DB Error")
    orchestrator.clean_old_logs(days_to_keep=30)

def test_clean_old_logs_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    db_session_mock.query.return_value.items = []
    def side_effect_query(*args, **kwargs):
        class MockQuery:
            def __init__(self, n):
                self.n = n
            def filter(self, *a, **k):
                return self
            def first(self):
                return None
            def delete(self):
                return 5
        return MockQuery(db_session_mock.query.call_count)
    db_session_mock.query.side_effect = side_effect_query
    orchestrator.clean_old_logs(days_to_keep=None)
    db_session_mock.add.assert_called_once()

def test_clean_old_logs_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    db_session_mock.query.return_value.items = []
    def side_effect_query(*args, **kwargs):
        class MockQuery:
            def __init__(self, n):
                self.n = n
            def filter(self, *a, **k):
                return self
            def first(self):
                return None
            def delete(self):
                return 5
        return MockQuery(db_session_mock.query.call_count)
    db_session_mock.query.side_effect = side_effect_query
    db_session_mock.add.side_effect = SQLAlchemyError("DB Error")
    orchestrator.clean_old_logs(days_to_keep=30)

def test_execute_manual_backup_telegram_backup_fails(orchestrator, mock_backup_service):
    mock_backup_service.create_safe_backup.return_value = None
    orchestrator.execute_manual_backup_telegram()

def test_execute_manual_backup_telegram_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_telegram_service, mock_os):
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_telegram_service.send_document.return_value = True
    orchestrator.execute_manual_backup_telegram()
    db_session_mock.add.assert_called_once()
    mock_os[1].assert_any_call("/tmp/backup.zip")

def test_execute_manual_backup_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_telegram_service, mock_os):
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_telegram_service.send_document.return_value = False
    orchestrator.execute_manual_backup_telegram()
    db_session_mock.add.assert_called_once()

def test_execute_manual_backup_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_backup_service, mock_telegram_service, mock_os):
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_telegram_service.send_document.return_value = True
    db_session_mock.add.side_effect = SQLAlchemyError("DB Error")
    orchestrator.execute_manual_backup_telegram()

def test_send_manual_report_telegram_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_telegram_service):
    mock_telegram_service.generate_report_text.side_effect = SQLAlchemyError("DB Error")
    orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())

def test_send_manual_report_telegram_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_telegram_service, mock_os, mock_get_log_path):
    mock_telegram_service.generate_report_text.return_value = "Report"
    mock_telegram_service.send_text.return_value = True
    orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())
    db_session_mock.add.assert_called_once()

def test_send_manual_report_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_telegram_service, mock_os, mock_get_log_path):
    mock_telegram_service.generate_report_text.return_value = "Report"
    mock_telegram_service.send_text.return_value = False
    orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())
    db_session_mock.add.assert_called_once()

def test_send_manual_report_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock, mock_telegram_service, mock_os, mock_get_log_path):
    mock_telegram_service.generate_report_text.return_value = "Report"
    mock_telegram_service.send_text.return_value = True
    db_session_mock.add.side_effect = SQLAlchemyError("DB Error")
    orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())

def test_send_manual_backup_email_no_smtp(orchestrator):
    with patch.object(settings, 'SMTP_HOST', None):
        with pytest.raises(HTTPException):
            orchestrator.send_manual_backup_email(None)

def test_send_manual_backup_email_no_maintainers(orchestrator, db_session_mock, mock_get_db_session):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(settings, 'SMTP_PASSWORD', 'pass'):
        db_session_mock.query.return_value.items = []
        with pytest.raises(HTTPException):
            orchestrator.send_manual_backup_email(None)

def test_send_manual_backup_email_backup_fails(orchestrator, db_session_mock, mock_get_db_session, mock_daily_report_service, mock_backup_service):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(settings, 'SMTP_PASSWORD', 'pass'):
        db_session_mock.query.return_value.items = [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        mock_backup_service.create_safe_backup.return_value = None
        with pytest.raises(HTTPException):
            orchestrator.send_manual_backup_email(None)

def test_send_manual_backup_email_success(orchestrator, db_session_mock, mock_get_db_session, mock_daily_report_service, mock_backup_service, mock_email_service, mock_os, mock_get_log_path, mock_datetime):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(settings, 'SMTP_PASSWORD', 'pass'):
        db_session_mock.query.return_value.items = [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = True
        res = orchestrator.send_manual_backup_email(None)
        assert res is True
        mock_os[1].assert_any_call("/tmp/backup.zip")

def test_send_manual_backup_email_send_fails(orchestrator, db_session_mock, mock_get_db_session, mock_daily_report_service, mock_backup_service, mock_email_service, mock_os, mock_get_log_path, mock_datetime):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(settings, 'SMTP_PASSWORD', 'pass'):
        db_session_mock.query.return_value.items = [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = False
        with pytest.raises(HTTPException):
            orchestrator.send_manual_backup_email(db_session_mock)
