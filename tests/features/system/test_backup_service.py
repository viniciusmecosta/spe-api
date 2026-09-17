from unittest.mock import MagicMock, mock_open, patch

from app.features.system.backup_service import BackupService


def test_create_safe_backup_success(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_schema", return_value=True)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.getsize", return_value=1024)

    result = service.create_safe_backup()

    assert result is not None
    assert result.startswith("temp_backup_")
    assert result.endswith(".sql")


def test_create_safe_backup_dump_failure(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_schema", return_value=False)
    mocker.patch("os.path.exists", return_value=False)

    result = service.create_safe_backup()
    assert result is None


def test_create_safe_backup_exception(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_schema", side_effect=Exception("PG Dump error"))
    mock_logger = mocker.patch("app.features.system.backup_service.logger.exception")

    result = service.create_safe_backup()
    assert result is None
    mock_logger.assert_called_once()


def test_create_sql_dump_success(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_inserts", return_value=True)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.getsize", return_value=1024)
    result = service.create_sql_dump()
    assert result is not None
    assert result.startswith("temp_inserts_")
    assert result.endswith(".sql")


def test_create_sql_dump_failure(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_inserts", return_value=False)
    mocker.patch("os.path.exists", return_value=False)
    assert service.create_sql_dump() is None


def test_compress_files_success(mocker):
    mock_zipfile = mocker.patch("app.features.system.backup_service.zipfile.ZipFile")
    mock_exists = mocker.patch("app.features.system.backup_service.os.path.exists",
                               side_effect=lambda p: p != "missing.db")

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
    mocker.patch("app.features.system.backup_service.zipfile.ZipFile", side_effect=Exception("Zip error"))
    mock_logger = mocker.patch("app.features.system.backup_service.logger.exception")

    service = BackupService()
    result = service.compress_files({"file1.db": "backup1.db"}, "output.zip")

    assert result is None
    mock_logger.assert_called_once()


def test_dump_postgresql_tier1_pg_dump_success(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value="/usr/bin/pg_dump")
    proc_mock = MagicMock()
    proc_mock.stdout = b"-- pg_dump dump"
    mocker.patch("subprocess.run", return_value=proc_mock)
    mocker.patch.object(service, "_filter_pg_dump_output", return_value=True)

    result = service._dump_postgresql_inserts("output.sql")
    assert result is True


def test_dump_postgresql_tier2_docker_success(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value=None)
    mocker.patch("shutil.which", side_effect=lambda cmd: "/usr/bin/docker" if cmd == "docker" else None)
    proc_mock = MagicMock()
    proc_mock.stdout = b"-- pg_dump dump"
    mocker.patch("subprocess.run", return_value=proc_mock)
    mocker.patch.object(service, "_filter_pg_dump_output", return_value=True)

    result = service._dump_postgresql_inserts("output.sql")
    assert result is True


def test_dump_postgresql_tier3_python_fallback(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value=None)
    mocker.patch("shutil.which", return_value=None)
    mock_py_dump = mocker.patch.object(service, "_dump_postgresql_python", return_value=True)

    result = service._dump_postgresql_inserts("output.sql")
    assert result is True
    mock_py_dump.assert_called_once()


def test_dump_postgresql_python_success(mocker):
    service = BackupService()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.side_effect = [
        [("companies",)],  # table_names
        [(1, "Company A", {"k": "v"}, memoryview(b"abc"))],  # row
    ]
    mock_cur.description = [("id",), ("name",), ("data",), ("blob",)]
    mock_cur.fetchone.return_value = ("companies_id_seq",)
    mock_cur.mogrify.return_value = b'INSERT INTO "companies" ("id") VALUES (1);\n'

    mocker.patch("psycopg2.connect", return_value=mock_conn)
    mocker.patch("builtins.open", mocker.mock_open())

    params = {"host": "localhost", "port": 5432, "user": "spe", "password": "pwd", "dbname": "spe_db"}
    result = service._dump_postgresql_python("output.sql", params)

    assert result is True
    mock_conn.close.assert_called_once()


def test_dump_postgresql_python_failure(mocker):
    service = BackupService()
    mocker.patch("psycopg2.connect", side_effect=Exception("DB Connection Error"))
    mock_logger = mocker.patch("app.features.system.backup_service.logger.exception")

    params = {"host": "localhost", "port": 5432, "user": "spe", "password": "pwd", "dbname": "spe_db"}
    result = service._dump_postgresql_python("output.sql", params)

    assert result is False
    mock_logger.assert_called_once()
