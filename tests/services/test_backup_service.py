import sqlite3
import pytest
from unittest.mock import MagicMock, mock_open, patch

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

def test_create_sql_dump_success(mocker):
    mock_connect = mocker.patch("app.services.backup_service.sqlite3.connect")
    conn = MagicMock()
    conn.iterdump.return_value = ["CREATE TABLE test;", "INSERT INTO test VALUES(1);"]
    mock_connect.return_value = conn
    
    m = mock_open()
    with patch("builtins.open", m):
        service = BackupService()
        result = service.create_sql_dump("test.db")
        
    assert result == "test.sql"
    conn.close.assert_called_once()
    m.assert_called_once_with("test.sql", "w", encoding="utf-8")

def test_create_sql_dump_failure(mocker):
    mock_connect = mocker.patch("app.services.backup_service.sqlite3.connect")
    mock_connect.side_effect = Exception("DB error")
    mock_logger = mocker.patch("app.services.backup_service.logger.exception")
    
    service = BackupService()
    result = service.create_sql_dump("test.db")
    
    assert result is None
    mock_logger.assert_called_once()

def test_compress_files_success(mocker):
    mock_zipfile = mocker.patch("app.services.backup_service.zipfile.ZipFile")
    mock_exists = mocker.patch("app.services.backup_service.os.path.exists", side_effect=lambda p: p != "missing.db")
    
    zip_instance = MagicMock()
    mock_zipfile.return_value.__enter__.return_value = zip_instance
    
    service = BackupService()
    files = {
        "file1.db": "backup1.db",
        "missing.db": "missing.db",
        "": "empty.db"
    }
    result = service.compress_files(files, "output.zip")
    
    assert result == "output.zip"
    zip_instance.write.assert_called_once_with("file1.db", arcname="backup1.db")

def test_compress_files_failure(mocker):
    mocker.patch("app.services.backup_service.zipfile.ZipFile", side_effect=Exception("Zip error"))
    mock_logger = mocker.patch("app.services.backup_service.logger.exception")
    
    service = BackupService()
    result = service.compress_files({"file1.db": "backup1.db"}, "output.zip")
    
    assert result is None
    mock_logger.assert_called_once()
