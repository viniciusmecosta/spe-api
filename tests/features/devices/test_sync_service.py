import sqlite3
from unittest.mock import MagicMock

import requests
from sqlalchemy.exc import SQLAlchemyError

import pytest
from app.features.devices.device_exceptions import (
    SyncConsumerOnlyError,
    SyncDatabaseCorruptedError,
    SyncDatabaseReceiveError,
)
from app.features.devices.sync_service import sync_service
from app.features.system.system_models import RoutineLog


@pytest.fixture
def sync_get_db_session(mocker, db_session_mock):
    mock = mocker.patch("app.features.devices.sync_service.get_db_session")

    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock.return_value = ContextManagerMock()
    return mock


def test_check_sqlite_integrity_success(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("ok",)
    mock_conn.cursor.return_value = mock_cursor
    mocker.patch("sqlite3.connect", return_value=mock_conn)
    result = sync_service._check_sqlite_integrity("test.db")
    assert result is True
    mock_cursor.execute.assert_called_once_with("PRAGMA integrity_check;")


def test_check_sqlite_integrity_failure(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("not_ok",)
    mock_conn.cursor.return_value = mock_cursor
    mocker.patch("sqlite3.connect", return_value=mock_conn)
    result = sync_service._check_sqlite_integrity("test.db")
    assert result is False


def test_check_sqlite_integrity_exception(mocker):
    mocker.patch("sqlite3.connect", side_effect=sqlite3.Error)
    result = sync_service._check_sqlite_integrity("test.db")
    assert result is False


def test_receive_database_wrong_mode(mocker):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mock_file = MagicMock()
    with pytest.raises(SyncConsumerOnlyError) as exc:
        sync_service.receive_database(mock_file)
    assert exc.value.status_code == 403


def test_receive_database_success(mocker):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "CONSUMIDOR")
    mock_file = MagicMock()
    mock_file.file.read.return_value = b"test"
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch.object(sync_service, "_check_sqlite_integrity", return_value=True)
    mocker.patch("app.features.devices.sync_service.engine.dispose")
    mocker.patch("os.replace")
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.remove")
    result = sync_service.receive_database(mock_file)
    assert result is True


def test_receive_database_invalid_integrity(mocker):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "CONSUMIDOR")
    mock_file = MagicMock()
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch.object(sync_service, "_check_sqlite_integrity", return_value=False)
    mocker.patch("os.remove")
    with pytest.raises(SyncDatabaseCorruptedError) as exc:
        sync_service.receive_database(mock_file)
    assert exc.value.status_code == 400


def test_receive_database_os_error(mocker):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "CONSUMIDOR")
    mock_file = MagicMock()
    mocker.patch("builtins.open", side_effect=OSError("Disk error"))
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.remove")
    with pytest.raises(SyncDatabaseReceiveError) as exc:
        sync_service.receive_database(mock_file)
    assert exc.value.status_code == 400


def test_send_database_wrong_mode(mocker):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "CONSUMIDOR")
    result = sync_service.send_database_to_consumer()
    assert result is None


def test_send_database_missing_config(mocker):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "")
    result = sync_service.send_database_to_consumer()
    assert result is None

    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "")
    result = sync_service.send_database_to_consumer()
    assert result is None


def test_send_database_already_exists(mocker, db_session_mock, sync_get_db_session):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "key")
    db_session_mock.query.return_value.items = [RoutineLog()]
    result = sync_service.send_database_to_consumer()
    assert result is None


def test_send_database_db_error_on_read(mocker, sync_get_db_session):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "key")

    class ExceptionContextManager:
        def __enter__(self):
            raise SQLAlchemyError("DB Error")

        def __exit__(self, *args):
            pass

    sync_get_db_session.return_value = ExceptionContextManager()
    result = sync_service.send_database_to_consumer()
    assert result is None


def test_send_database_backup_fails(mocker, db_session_mock, sync_get_db_session):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "key")
    db_session_mock.query.return_value.items = []
    mocker.patch("app.features.devices.sync_service.backup_service.create_safe_backup", return_value=None)
    result = sync_service.send_database_to_consumer()
    assert result is None


def test_send_database_success(mocker, db_session_mock, sync_get_db_session):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "key")
    db_session_mock.query.return_value.items = []
    mocker.patch("app.features.devices.sync_service.backup_service.create_safe_backup", return_value="backup.db")
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("requests.post")
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.remove")
    sync_service.send_database_to_consumer()
    assert db_session_mock.add.called


def test_send_database_request_exception(mocker, db_session_mock, sync_get_db_session):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "key")
    db_session_mock.query.return_value.items = []
    mocker.patch("app.features.devices.sync_service.backup_service.create_safe_backup", return_value="backup.db")
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("requests.post", side_effect=requests.RequestException("Req error"))
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.remove")
    sync_service.send_database_to_consumer()
    assert db_session_mock.add.called


def test_send_database_request_exception_and_db_error(mocker, db_session_mock, sync_get_db_session):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "key")
    db_session_mock.query.return_value.items = []
    mocker.patch("app.features.devices.sync_service.backup_service.create_safe_backup", return_value="backup.db")
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("requests.post", side_effect=requests.RequestException("Req error"))
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.remove")

    class ContextManagerMockErr:
        def __init__(self, mode):
            self.mode = mode
            self.call_count = 0

        def __enter__(self):
            self.call_count += 1
            if self.mode == "fail_on_second" and self.call_count == 2:
                raise SQLAlchemyError("DB Error")
            return db_session_mock

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    sync_get_db_session.side_effect = None
    sync_get_db_session.return_value = ContextManagerMockErr("fail_on_second")
    sync_service.send_database_to_consumer()


def test_send_database_db_error_on_write(mocker, db_session_mock, sync_get_db_session):
    mocker.patch("app.features.devices.sync_service.settings.OPERATION_MODE", "EXPORTADOR")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_SERVER_URL", "http://test")
    mocker.patch("app.features.devices.sync_service.settings.CONSUMER_API_KEY", "key")
    db_session_mock.query.return_value.items = []
    mocker.patch("app.features.devices.sync_service.backup_service.create_safe_backup", return_value="backup.db")
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("requests.post")
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.remove")

    class ContextManagerMockErr2:
        def __init__(self):
            self.call_count = 0

        def __enter__(self):
            self.call_count += 1
            if self.call_count == 2:
                raise SQLAlchemyError("DB Error")
            return db_session_mock

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    sync_get_db_session.side_effect = None
    sync_get_db_session.return_value = ContextManagerMockErr2()
    sync_service.send_database_to_consumer()
