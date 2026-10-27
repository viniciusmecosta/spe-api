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
    orc._repo.has_hourly_routine_run.return_value = False
    orc._repo.has_routine_run_for_target_date.return_value = False
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


@pytest.mark.parametrize("environment", ["dev", "test"])
async def test_automatic_backups_only_run_in_prod(orchestrator, environment):
    with patch.object(settings, "ENVIRONMENT", environment):
        await orchestrator.execute_hourly_backup_telegram()
        await orchestrator.run_daily_backup_routine_email()
    orchestrator._repo.has_hourly_routine_run.assert_not_called()
    orchestrator._repo.has_routine_run_for_target_date.assert_not_called()


async def test_execute_hourly_backup_telegram_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'HOURLY_BACKUP_START_HOUR', 14), patch.object(settings, 'HOURLY_BACKUP_END_HOUR', 18):
        await orchestrator.execute_hourly_backup_telegram()














async def test_send_managerial_report_telegram_out_of_hours(orchestrator, mock_datetime):
    with patch.object(settings, 'DAILY_REPORT_HOUR', 14):
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


async def test_clean_old_logs_preserves_dev_copy(orchestrator):
    with patch.object(settings, "ENVIRONMENT", "dev"):
        await orchestrator.clean_old_logs(days_to_keep=30)
    orchestrator._repo.has_routine_run_for_target_date.assert_not_called()
    orchestrator._repo.delete_older_than.assert_not_called()
    orchestrator._repo.log_execution.assert_not_called()


async def test_clean_old_logs_db_error_on_write(orchestrator, mock_datetime, mock_get_db_session, db_session_mock):
    orchestrator._repo.has_routine_run_for_target_date.return_value = False
    orchestrator._repo.delete_older_than.return_value = 5
    orchestrator._repo.log_execution.side_effect = SQLAlchemyError("DB Error")
    await orchestrator.clean_old_logs(days_to_keep=30)




































def test_generate_backup_files_zip_sync_postgresql(mocker):
    orchestrator = RoutineOrchestrator()
    mocker.patch("app.features.system.routine_orchestrator.backup_service.consistent_snapshot")
    mocker.patch("app.features.system.routine_orchestrator.backup_service.create_safe_backup",
                 return_value="temp_backup.sql")
    mocker.patch("app.features.system.routine_orchestrator.backup_service.create_sql_dump",
                 return_value="temp_inserts.sql")
    mock_compress = mocker.patch("app.features.system.routine_orchestrator.backup_service.compress_files",
                                 return_value="temp_backup.sql.zip.enc")

    b_path, s_path, z_path = orchestrator._generate_backup_files_zip_sync()
    assert b_path == "temp_backup.sql"
    assert s_path == "temp_inserts.sql"
    assert z_path == "temp_backup.sql.zip.enc"

    mock_compress.assert_called_once_with(
        {"temp_backup.sql": "spe-db.sql", "temp_inserts.sql": "spe_dump.sql"},
        "temp_backup.sql.zip"
    )


def test_generate_backup_files_zip_sync_requires_schema_and_data(mocker):
    orchestrator = RoutineOrchestrator()
    mocker.patch("app.features.system.routine_orchestrator.backup_service.consistent_snapshot")
    mocker.patch("app.features.system.routine_orchestrator.backup_service.create_safe_backup", return_value="schema.sql")
    mocker.patch("app.features.system.routine_orchestrator.backup_service.create_sql_dump", return_value=None)
    mock_compress = mocker.patch("app.features.system.routine_orchestrator.backup_service.compress_files")

    assert orchestrator._generate_backup_files_zip_sync() == (None, None, None)
    mock_compress.assert_not_called()


@pytest.mark.asyncio
async def test_build_email_attachments_postgresql(mocker):
    orchestrator = RoutineOrchestrator()
    mocker.patch("os.path.exists", return_value=True)

    att_unzipped = await orchestrator._build_email_attachments(
        "backup.sql",
        datetime(2023, 1, 1).date(),
        datetime(2023, 1, 2).date(),
    )
    filenames_unzipped = [a[1] for a in att_unzipped]
    assert "spe-db.sql" not in filenames_unzipped
    assert "spe_dump.sql" not in filenames_unzipped

    att_zip = await orchestrator._build_email_attachments(
        "backup.sql.zip.enc",
        datetime(2023, 1, 1).date(),
        datetime(2023, 1, 2).date(),
    )
    filenames_zip = [a[1] for a in att_zip]
    assert "spe.zip.enc" in filenames_zip
    assert "spe_dump.sql" not in filenames_zip
    assert "spe-db.sql" not in filenames_zip
    assert any(f.startswith("log_") for f in filenames_zip)






@pytest.mark.asyncio
async def test_resolve_backup_filename(orchestrator):
    assert orchestrator._resolve_backup_filename("path.zip", None) == "spe.zip"
    assert orchestrator._resolve_backup_filename("path.zip.enc", None) == "spe.zip.enc"
    assert orchestrator._resolve_backup_filename(None, "path.sql") == "spe-db.sql"
    assert orchestrator._resolve_backup_filename(None, None) == "spe_dump.sql"


@pytest.mark.asyncio
async def test_prepare_backup_attachments_branches(orchestrator, mocker):
    mocker.patch("os.path.exists", return_value=True)
    att = []
    orchestrator._prepare_backup_attachments(att, "spe.zip.enc")
    assert att == [("spe.zip.enc", "spe.zip.enc")]

    att2 = []
    orchestrator._prepare_backup_attachments(att2, None)
    assert att2 == []

    att3 = []
    orchestrator._prepare_backup_attachments(att3, None)
    assert att3 == []










@pytest.mark.parametrize(('method', 'routine', 'scheduled'), [
    ('execute_hourly_backup_telegram', 'TELEGRAM_HOURLY_BACKUP', True),
    ('send_managerial_report_telegram', 'TELEGRAM_DAILY_REPORT', True),
    ('run_daily_backup_routine_email', 'EMAIL_DAILY_BACKUP', True),
    ('execute_manual_backup_telegram', 'TELEGRAM_MANUAL_BACKUP', False),
    ('send_manual_backup_email', 'EMAIL_MANUAL_BACKUP', False),
])
async def test_routines_persist_before_sending(orchestrator, mock_get_db_session, mock_datetime, mocker, method, routine, scheduled):
    submit = mocker.patch('app.features.system.routine_orchestrator.submit', new_callable=AsyncMock, return_value=42)
    assert await getattr(orchestrator, method)() == 42
    kind, payload, key = submit.await_args.args
    assert kind == 'NOTIFICATION'
    assert payload['routine_type'] == routine
    assert payload['start_date'] == '2023-10-14'
    assert bool(key) == scheduled


async def test_manual_report_preserves_requested_period(orchestrator, mocker):
    from datetime import date
    submit = mocker.patch('app.features.system.routine_orchestrator.submit', new_callable=AsyncMock, return_value=42)
    await orchestrator.send_manual_report_telegram(date(2026, 10, 1), date(2026, 10, 5))
    assert submit.await_args.args[1]['start_date'] == '2026-10-01'
    assert submit.await_args.args[1]['end_date'] == '2026-10-05'


async def test_job_database_failure_does_not_report_success(orchestrator, mocker):
    mocker.patch('app.features.system.routine_orchestrator.submit', new_callable=AsyncMock, side_effect=SQLAlchemyError('unavailable'))
    with pytest.raises(SQLAlchemyError):
        await orchestrator.execute_manual_backup_telegram()


async def test_routine_orchestrator_remaining_branches(orchestrator, mock_get_db_session, db_session_mock, mocker, tmp_path):
    from datetime import date

    assert EmailNotConfiguredError().status_code == 400
    assert NoMaintainersWithEmailError().status_code == 400
    assert BackupGenerationFailedError().status_code == 400
    assert SMTPConnectionFailedError().status_code == 400

    orchestrator._repo.has_hourly_routine_run.return_value = True
    assert await orchestrator.execute_hourly_backup_telegram() is None

    mocker.patch("app.features.system.routine_orchestrator.backup_service.consistent_snapshot")
    mocker.patch("app.features.system.routine_orchestrator.backup_service.create_safe_backup", return_value="b.sql")
    mocker.patch("app.features.system.routine_orchestrator.backup_service.create_sql_dump", return_value="d.sql")
    mocker.patch("app.features.system.routine_orchestrator.backup_service.compress_files", return_value="b.zip")
    assert orchestrator._generate_backup_files_zip_sync() == (None, None, None)

    mocker.patch.object(orchestrator, "_generate_backup_files_zip_sync", return_value=("b", "s", "z.enc"))
    assert await orchestrator._generate_backup_files_zip() == ("b", "s", "z.enc")

    f_tmp = tmp_path / "temp.sql"
    f_tmp.write_text("sql")
    orchestrator._cleanup_backup_files_sync(str(f_tmp), None, None)
    assert not f_tmp.exists()

    f_err = tmp_path / "err.sql"
    f_err.write_text("sql")
    mocker.patch("app.features.system.routine_orchestrator.os.remove", side_effect=OSError("perm"))
    orchestrator._cleanup_backup_files_sync(str(f_err), None, None)
    await orchestrator._cleanup_backup_files(str(f_err), None, None)

    await orchestrator._log_daily_backup_email_execution(True, date(2026, 1, 1), datetime(2026, 1, 2, 1, 0))
    await orchestrator._log_daily_backup_email_execution(False, date(2026, 1, 1), datetime(2026, 1, 2, 1, 0))
    orchestrator._repo.log_execution.side_effect = SQLAlchemyError("err")
    await orchestrator._log_daily_backup_email_execution(True, date(2026, 1, 1), datetime(2026, 1, 2, 1, 0))

    mocker.patch("app.features.system.routine_orchestrator.os.path.exists", return_value=True)
    mock_send_doc = mocker.patch("app.features.system.routine_orchestrator.telegram_service.send_document")
    await orchestrator._send_system_logs_telegram(date(2026, 1, 1), date(2026, 1, 2))
    assert mock_send_doc.call_count == 2

    mock_scalars_empty = MagicMock()
    mock_scalars_empty.all.return_value = []
    db_session_mock.scalars = AsyncMock(return_value=mock_scalars_empty)
    with pytest.raises(NoMaintainersWithEmailError):
        await orchestrator._fetch_manual_backup_report(db_session_mock)

    maint = User(id=1, role=UserRole.MAINTAINER, is_active=True, email="m@m.com")
    mock_scalars_maint = MagicMock()
    mock_scalars_maint.all.return_value = [maint]
    db_session_mock.scalars = AsyncMock(return_value=mock_scalars_maint)
    mocker.patch(
        "app.features.system.routine_orchestrator.daily_report_service.generate_daily_report_html",
        new_callable=AsyncMock,
        return_value="<p>html</p>",
    )
    emails, html, period_text, _, _ = await orchestrator._fetch_manual_backup_report(db_session_mock)
    assert emails == ["m@m.com"]
    assert html == "<p>html</p>"
    assert "relatório" in period_text

    mock_job = MagicMock(id=77)
    mocker.patch("app.features.system.routine_orchestrator.enqueue", new_callable=AsyncMock, return_value=mock_job)
    audit_svc = MagicMock()
    audit_svc.async_log = AsyncMock()
    res = await orchestrator.trigger_manual_backup_email(maint, audit_svc)
    assert res["job_id"] == "77"
