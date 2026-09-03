from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

import pytest
from app.core.config import settings
from app.features.system.routine_orchestrator import RoutineOrchestrator
from app.features.system.system_exceptions import (
    BackupGenerationFailedError,
    EmailNotConfiguredError,
    NoMaintainersWithEmailError,
    SMTPConnectionFailedError,
)
from app.features.users.user_models import User
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_environment():
    with patch("app.features.system.routine_orchestrator.settings.ENVIRONMENT", "prod"):
        yield


@pytest.fixture
def mock_get_db_session(db_session_mock):
    with patch("app.features.system.routine_orchestrator.get_async_session_context") as m:
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return db_session_mock

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        m.return_value = AsyncContextManagerMock()
        yield m


@pytest.fixture
def orchestrator():
    orc = RoutineOrchestrator()
    orc._repo = AsyncMock()
    return orc


@pytest.fixture
def mock_datetime():
    with patch("app.features.system.routine_orchestrator.datetime") as dt_mock:
        dt_mock.now.return_value = datetime(2023, 10, 15, 12, 0, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
        yield dt_mock


@pytest.fixture
def mock_backup_service():
    with patch("app.features.system.routine_orchestrator.backup_service") as m:
        yield m


@pytest.fixture
def mock_telegram_service():
    with patch("app.features.system.routine_orchestrator.telegram_service") as m:
        m.generate_report_text = AsyncMock()
        yield m


@pytest.fixture
def mock_email_service():
    with patch("app.features.system.routine_orchestrator.email_service") as m:
        yield m


@pytest.fixture
def mock_daily_report_service():
    with patch("app.features.system.routine_orchestrator.daily_report_service") as m:
        yield m


@pytest.fixture
def mock_os():
    with patch("app.features.system.routine_orchestrator.os.path.exists", return_value=True) as m1, \
            patch("app.features.system.routine_orchestrator.os.remove") as m2:
        yield m1, m2


@pytest.fixture
def mock_get_log_path():
    with patch("app.features.system.routine_orchestrator.get_log_path", return_value="/tmp/test.log") as m:
        yield m


async def test_execute_hourly_backup_telegram_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 14), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        await orchestrator.execute_hourly_backup_telegram()


async def test_execute_hourly_backup_telegram_already_exists(orchestrator, mock_datetime, mock_get_db_session,
                                                             db_session_mock):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        orchestrator._repo.has_hourly_routine_run.return_value = True
        await orchestrator.execute_hourly_backup_telegram()


async def test_execute_hourly_backup_telegram_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session,
                                                               db_session_mock):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        orchestrator._repo.has_hourly_routine_run.side_effect = SQLAlchemyError("DB Error")
        await orchestrator.execute_hourly_backup_telegram()


async def test_execute_hourly_backup_telegram_backup_fails(orchestrator, mock_datetime, mock_get_db_session,
                                                           db_session_mock,
                                                           mock_backup_service):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        orchestrator._repo.has_hourly_routine_run.return_value = False
        mock_backup_service.create_safe_backup.return_value = None
        await orchestrator.execute_hourly_backup_telegram()


async def test_execute_hourly_backup_telegram_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock,
                                                      mock_backup_service, mock_telegram_service, mock_os):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        orchestrator._repo.has_hourly_routine_run.return_value = False
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_telegram_service.send_document.return_value = True
        await orchestrator.execute_hourly_backup_telegram()
        orchestrator._repo.log_execution.assert_called_once()
        mock_os[1].assert_any_call("/tmp/backup.zip")


async def test_execute_hourly_backup_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session,
                                                         db_session_mock,
                                                         mock_backup_service, mock_telegram_service, mock_os):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        orchestrator._repo.has_hourly_routine_run.return_value = False
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_telegram_service.send_document.return_value = False
        await orchestrator.execute_hourly_backup_telegram()
        orchestrator._repo.log_execution.assert_not_called()


async def test_execute_hourly_backup_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session,
                                                                db_session_mock, mock_backup_service,
                                                                mock_telegram_service,
                                                                mock_os):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 10), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        orchestrator._repo.has_hourly_routine_run.return_value = False
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_telegram_service.send_document.return_value = True
        orchestrator._repo.log_execution.side_effect = SQLAlchemyError("DB Error")
        await orchestrator.execute_hourly_backup_telegram()


async def test_send_managerial_report_telegram_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 14):
        await orchestrator.send_managerial_report_telegram()


async def test_send_managerial_report_telegram_already_ran(orchestrator, mock_datetime, mock_get_db_session,
                                                           db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = True
        await orchestrator.send_managerial_report_telegram()


async def test_send_managerial_report_telegram_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session,
                                                                db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.side_effect = SQLAlchemyError("DB Error")
        await orchestrator.send_managerial_report_telegram()


async def test_send_managerial_report_telegram_success_with_previous(orchestrator, mock_datetime, mock_get_db_session,
                                                                     db_session_mock, mock_telegram_service,
                                                                     mock_get_log_path, mock_os):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        orchestrator._repo.get_last_successful_target_date.return_value = datetime(2023, 10, 13).date()
        mock_telegram_service.generate_report_text.return_value = "Report"
        mock_telegram_service.send_text.return_value = True
        await orchestrator.send_managerial_report_telegram()
        orchestrator._repo.log_execution.assert_called_once()
        mock_telegram_service.send_document.assert_called()


async def test_send_managerial_report_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session,
                                                          db_session_mock,
                                                          mock_telegram_service, mock_get_log_path, mock_os):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        orchestrator._repo.get_last_successful_target_date.return_value = None
        mock_telegram_service.generate_report_text.return_value = "Report"
        mock_telegram_service.send_text.return_value = False
        await orchestrator.send_managerial_report_telegram()
        orchestrator._repo.log_execution.assert_called_once()


async def test_send_managerial_report_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session,
                                                                 db_session_mock, mock_telegram_service,
                                                                 mock_get_log_path,
                                                                 mock_os):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        orchestrator._repo.get_last_successful_target_date.return_value = None
        mock_telegram_service.generate_report_text.return_value = "Report"
        mock_telegram_service.send_text.return_value = True
        orchestrator._repo.log_execution.side_effect = SQLAlchemyError("DB Error")
        await orchestrator.send_managerial_report_telegram()


async def test_generate_daily_backup_report(orchestrator, db_session_mock, mock_daily_report_service, mock_get_log_path,
                                            mock_os):
    mock_daily_report_service.generate_daily_report_html = AsyncMock()
    mock_daily_report_service.generate_daily_report_html.return_value = "<p>Report</p>"
    html, att, p_text = await orchestrator._generate_daily_backup_report(
        db_session_mock,
        datetime(2023, 10, 13).date(),
        datetime(2023, 10, 14).date()
    )
    assert "<p>Report</p>" in html
    assert len(att) == 2


async def test_generate_daily_backup_report_empty(orchestrator, db_session_mock, mock_daily_report_service,
                                                  mock_get_log_path):
    with patch("app.features.system.routine_orchestrator.os.path.exists", return_value=False):
        mock_daily_report_service.generate_daily_report_html = AsyncMock()
        mock_daily_report_service.generate_daily_report_html.return_value = ""
        html, att, p_text = await orchestrator._generate_daily_backup_report(
            db_session_mock,
            datetime(2023, 10, 14).date(),
            datetime(2023, 10, 14).date()
        )
        assert "Nenhum período" in html
        assert len(att) == 0


async def test_run_daily_backup_routine_email_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 14):
        await orchestrator.run_daily_backup_routine_email()


async def test_run_daily_backup_routine_email_already_ran(orchestrator, mock_datetime, mock_get_db_session,
                                                          db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = True
        await orchestrator.run_daily_backup_routine_email()


async def test_run_daily_backup_routine_email_no_maintainers(orchestrator, mock_datetime, mock_get_db_session,
                                                             db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        await orchestrator.run_daily_backup_routine_email()


async def test_run_daily_backup_routine_email_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session,
                                                               db_session_mock):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.side_effect = SQLAlchemyError("DB Error")
        await orchestrator.run_daily_backup_routine_email()


async def test_run_daily_backup_routine_email_backup_fails(orchestrator, mock_datetime, mock_get_db_session,
                                                           db_session_mock,
                                                           mock_backup_service):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        orchestrator._repo.get_last_successful_target_date.return_value = datetime(2023, 10, 13).date()
        mock_backup_service.create_safe_backup.return_value = None
        await orchestrator.run_daily_backup_routine_email()


async def test_run_daily_backup_routine_email_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock,
                                                      mock_backup_service, mock_email_service,
                                                      mock_daily_report_service,
                                                      mock_os, mock_get_log_path):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        orchestrator._repo.get_last_successful_target_date.return_value = None
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = True
        mock_daily_report_service.generate_daily_report_html = AsyncMock()
        mock_daily_report_service.generate_daily_report_html.return_value = ""
        await orchestrator.run_daily_backup_routine_email()
        orchestrator._repo.log_execution.assert_called_once()
        mock_os[1].assert_any_call("/tmp/backup.zip")


async def test_run_daily_backup_routine_email_send_fails(orchestrator, mock_datetime, mock_get_db_session,
                                                         db_session_mock,
                                                         mock_backup_service, mock_email_service,
                                                         mock_daily_report_service,
                                                         mock_os, mock_get_log_path):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        orchestrator._repo.get_last_successful_target_date.return_value = None
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = False
        mock_daily_report_service.generate_daily_report_html = AsyncMock()
        mock_daily_report_service.generate_daily_report_html.return_value = ""
        await orchestrator.run_daily_backup_routine_email()
        orchestrator._repo.log_execution.assert_called_once()


async def test_run_daily_backup_routine_email_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session,
                                                                db_session_mock, mock_backup_service,
                                                                mock_email_service,
                                                                mock_daily_report_service, mock_os, mock_get_log_path):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 10):
        orchestrator._repo.has_routine_run_for_target_date.return_value = False
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        orchestrator._repo.get_last_successful_target_date.return_value = None
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = True
        mock_daily_report_service.generate_daily_report_html = AsyncMock()
        mock_daily_report_service.generate_daily_report_html.return_value = ""
        orchestrator._repo.log_execution.side_effect = SQLAlchemyError("DB Error")
        await orchestrator.run_daily_backup_routine_email()


async def test_clean_old_logs_already_ran(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    orchestrator._repo.has_routine_run_for_target_date.return_value = True
    await orchestrator.clean_old_logs(days_to_keep=30)


async def test_clean_old_logs_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    orchestrator._repo.has_routine_run_for_target_date.side_effect = SQLAlchemyError("DB Error")
    await orchestrator.clean_old_logs(days_to_keep=30)


async def test_clean_old_logs_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    orchestrator._repo.has_routine_run_for_target_date.return_value = False
    orchestrator._repo.delete_older_than.return_value = 5
    await orchestrator.clean_old_logs(days_to_keep=None)
    orchestrator._repo.log_execution.assert_called_once()


async def test_clean_old_logs_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    orchestrator._repo.has_routine_run_for_target_date.return_value = False
    orchestrator._repo.delete_older_than.return_value = 5
    orchestrator._repo.log_execution.side_effect = SQLAlchemyError("DB Error")
    await orchestrator.clean_old_logs(days_to_keep=30)


async def test_execute_manual_backup_telegram_backup_fails(orchestrator, mock_backup_service):
    mock_backup_service.create_safe_backup.return_value = None
    await orchestrator.execute_manual_backup_telegram()


async def test_execute_manual_backup_telegram_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock,
                                                      mock_backup_service, mock_telegram_service, mock_os):
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_telegram_service.send_document.return_value = True
    await orchestrator.execute_manual_backup_telegram()
    orchestrator._repo.log_execution.assert_called_once()
    mock_os[1].assert_any_call("/tmp/backup.zip")


async def test_execute_manual_backup_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session,
                                                         db_session_mock,
                                                         mock_backup_service, mock_telegram_service, mock_os):
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_telegram_service.send_document.return_value = False
    await orchestrator.execute_manual_backup_telegram()
    orchestrator._repo.log_execution.assert_called_once()


async def test_execute_manual_backup_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session,
                                                                db_session_mock, mock_backup_service,
                                                                mock_telegram_service,
                                                                mock_os):
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_telegram_service.send_document.return_value = True
    orchestrator._repo.log_execution.side_effect = SQLAlchemyError("DB Error")
    await orchestrator.execute_manual_backup_telegram()


async def test_send_manual_report_telegram_db_error_on_read(orchestrator, mock_datetime, mock_get_db_session,
                                                            db_session_mock,
                                                            mock_telegram_service):
    mock_telegram_service.generate_report_text.side_effect = SQLAlchemyError("DB Error")
    await orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())


async def test_send_manual_report_telegram_success(orchestrator, mock_datetime, mock_get_db_session, db_session_mock,
                                                   mock_telegram_service, mock_os, mock_get_log_path):
    mock_telegram_service.generate_report_text.return_value = "Report"
    mock_telegram_service.send_text.return_value = True
    await orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())
    orchestrator._repo.log_execution.assert_called_once()


async def test_send_manual_report_telegram_send_fails(orchestrator, mock_datetime, mock_get_db_session, db_session_mock,
                                                      mock_telegram_service, mock_os, mock_get_log_path):
    mock_telegram_service.generate_report_text.return_value = "Report"
    mock_telegram_service.send_text.return_value = False
    await orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())
    orchestrator._repo.log_execution.assert_called_once()


async def test_send_manual_report_telegram_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session,
                                                             db_session_mock, mock_telegram_service, mock_os,
                                                             mock_get_log_path):
    mock_telegram_service.generate_report_text.return_value = "Report"
    mock_telegram_service.send_text.return_value = True
    orchestrator._repo.log_execution.side_effect = SQLAlchemyError("DB Error")
    await orchestrator.send_manual_report_telegram(datetime(2023, 10, 13).date(), datetime(2023, 10, 14).date())


async def test_send_manual_backup_email_no_smtp(orchestrator):
    with patch.object(settings, 'SMTP_HOST', None):
        with pytest.raises(EmailNotConfiguredError):
            await orchestrator.send_manual_backup_email(None)


async def test_send_manual_backup_email_no_maintainers(orchestrator, db_session_mock, mock_get_db_session):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(
            settings, 'SMTP_PASSWORD', 'pass'):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        with pytest.raises(NoMaintainersWithEmailError):
            await orchestrator.send_manual_backup_email(db_session_mock)


async def test_send_manual_backup_email_backup_fails(orchestrator, db_session_mock, mock_get_db_session,
                                                     mock_daily_report_service, mock_backup_service):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(
            settings, 'SMTP_PASSWORD', 'pass'):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        mock_backup_service.create_safe_backup.return_value = None
        mock_daily_report_service.generate_daily_report_html = AsyncMock(return_value="")
        with pytest.raises(BackupGenerationFailedError):
            await orchestrator.send_manual_backup_email(db_session_mock)


async def test_send_manual_backup_email_success(orchestrator, db_session_mock, mock_get_db_session,
                                                mock_daily_report_service,
                                                mock_backup_service, mock_email_service, mock_os, mock_get_log_path,
                                                mock_datetime):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(
            settings, 'SMTP_PASSWORD', 'pass'):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = True
        mock_daily_report_service.generate_daily_report_html = AsyncMock()
        mock_daily_report_service.generate_daily_report_html.return_value = ""
        res = await orchestrator.send_manual_backup_email(db_session_mock)
        assert res is True
        mock_os[1].assert_any_call("/tmp/backup.zip")


async def test_send_manual_backup_email_send_fails(orchestrator, db_session_mock, mock_get_db_session,
                                                   mock_daily_report_service, mock_backup_service, mock_email_service,
                                                   mock_os, mock_get_log_path, mock_datetime):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(
            settings, 'SMTP_PASSWORD', 'pass'):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = False
        mock_daily_report_service.generate_daily_report_html = AsyncMock()
        mock_daily_report_service.generate_daily_report_html.return_value = ""
        with pytest.raises(SMTPConnectionFailedError):
            await orchestrator.send_manual_backup_email(db_session_mock)


async def test_send_manual_backup_email_attaches_yesterday_and_today_logs(
        orchestrator, db_session_mock, mock_get_db_session,
        mock_daily_report_service, mock_backup_service, mock_email_service,
        mock_os, mock_get_log_path, mock_datetime,
):
    with patch.object(settings, 'SMTP_HOST', 'host'), patch.object(settings, 'SMTP_USER', 'user'), patch.object(
            settings, 'SMTP_PASSWORD', 'pass'):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            User(email="test@test.com", role=UserRole.MAINTAINER, is_active=True)]
        db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
        mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
        mock_email_service.send_email.return_value = True
        mock_daily_report_service.generate_daily_report_html = AsyncMock(return_value="")

        res = await orchestrator.send_manual_backup_email(db_session_mock)
        assert res is True
        call_attachments = mock_email_service.send_email.call_args[0][1]
        filenames = [att[1] for att in call_attachments]
        assert "spe.zip" in filenames
        log_files = [f for f in filenames if f.startswith("log_")]
        assert len(log_files) == 2


async def test_execute_manual_backup_telegram_sends_yesterday_and_today_logs(
        orchestrator, mock_datetime, mock_get_db_session, db_session_mock,
        mock_backup_service, mock_telegram_service, mock_os, mock_get_log_path,
):
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_telegram_service.send_document.return_value = True
    await orchestrator.execute_manual_backup_telegram()
    assert mock_telegram_service.send_document.call_count == 3


async def test_run_daily_backup_routine_email_attaches_today_log(
        orchestrator, mock_datetime, mock_get_db_session, db_session_mock,
        mock_daily_report_service, mock_backup_service, mock_email_service,
        mock_os, mock_get_log_path,
):
    orchestrator._repo.has_routine_run_for_target_date.return_value = False
    orchestrator._repo.get_last_successful_target_date.return_value = datetime(2023, 10, 14).date()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [User(email="admin@test.com", role=UserRole.MAINTAINER, is_active=True)]
    db_session_mock.scalars = AsyncMock(return_value=mock_scalars)
    mock_backup_service.create_safe_backup.return_value = "/tmp/backup.zip"
    mock_daily_report_service.generate_daily_report_html = AsyncMock(return_value="<p>Report</p>")
    mock_email_service.send_email.return_value = True

    with patch.object(settings, "DAILY_REPORT_HOUR", 10):
        await orchestrator.run_daily_backup_routine_email()

    assert mock_email_service.send_email.called
    attachments = mock_email_service.send_email.call_args[0][1]
    filenames = [att[1] for att in attachments]
    assert "spe.zip" in filenames
    log_files = [f for f in filenames if f.startswith("log_")]
    assert len(log_files) >= 2


async def test_routine_orchestrator_environment_dev_and_cleanup_oserror(orchestrator, mock_get_db_session,
                                                                        db_session_mock):
    with patch("os.path.exists", return_value=True), patch("os.remove", side_effect=OSError("Permission denied")):
        orchestrator._cleanup_backup_files_sync("a.bak", "b.sql", "c.zip")

    with patch.object(settings, "ENVIRONMENT", "dev"):
        res1 = await orchestrator.execute_hourly_backup_telegram()
        assert res1 is None
        res2 = await orchestrator.send_managerial_report_telegram()
        assert res2 is None

    orchestrator.db = None
    with patch.object(settings, "SMTP_HOST", "smtp.test.com"), \
            patch.object(settings, "SMTP_USER", "user"), \
            patch.object(settings, "SMTP_PASSWORD", "pass"), \
            patch.object(orchestrator, "_fetch_manual_backup_report", new_callable=AsyncMock) as mock_fetch, \
            patch.object(orchestrator, "_generate_backup_files_zip", new_callable=AsyncMock) as mock_gen, \
            patch.object(orchestrator, "_build_email_attachments", new_callable=AsyncMock) as mock_att, \
            patch("app.features.system.routine_orchestrator.email_service.send_email", return_value=True):
        mock_fetch.return_value = (["admin@test.com"], "html", "period", datetime(2023, 10, 14).date(),
                                   datetime(2023, 10, 15).date())
        mock_gen.return_value = ("/tmp/b.bak", None, None)
        mock_att.return_value = []
        success = await orchestrator.send_manual_backup_email(db=None)
        assert success is True
        mock_fetch.assert_awaited_once_with(db_session_mock)
