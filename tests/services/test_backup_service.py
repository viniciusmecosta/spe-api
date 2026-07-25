import sqlite3
import pytest
from unittest.mock import MagicMock

from app.services.backup_service import BackupService

def test_create_safe_backup_success(mocker, db_session_mock):
    mock_connect = mocker.patch("app.services.backup_service.sqlite3.connect")
    src_conn = MagicMock()
    dst_conn = MagicMock()
    mock_connect.side_effect = [src_conn, dst_conn]
    
    service = BackupService()
    result = service.create_safe_backup()
    
    assert result is not None
    assert result.startswith("temp_backup_")
    assert result.endswith(".db")
    
    assert mock_connect.call_count == 2
    src_conn.backup.assert_called_once_with(dst_conn, pages=100, sleep=0.05)
    dst_conn.close.assert_called_once()
    src_conn.close.assert_called_once()

def test_create_safe_backup_sqlite_error(mocker, db_session_mock):
    mock_connect = mocker.patch("app.services.backup_service.sqlite3.connect")
    mock_connect.side_effect = sqlite3.Error("Mocked SQLite error")
    
    mock_logger = mocker.patch("app.services.backup_service.logger.exception")
    
    service = BackupService()
    result = service.create_safe_backup()
    
    assert result is None
    mock_logger.assert_called_once()
