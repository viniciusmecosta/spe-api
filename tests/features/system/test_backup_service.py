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
        [("companies",), ("custom_table",)],
        [(1, "Company A", {"k": "v"}, memoryview(b"abc"))],
        [(10, "Custom")],
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


def test_get_postgres_connection_params_exception(mocker):
    service = BackupService()
    mocker.patch("sqlalchemy.engine.make_url", side_effect=Exception("Bad URL"))
    params = service._get_postgres_connection_params()
    assert params["host"] == "localhost"
    assert params["port"] == 5432
    assert params["user"] == "spe"
    assert params["dbname"] == "spe_db"


def test_dump_table_data_empty(mocker):
    service = BackupService()
    mock_cur = MagicMock()
    mock_cur.description = [("id",)]
    mock_cur.fetchall.return_value = []
    mock_file = MagicMock()
    service._dump_table_data(mock_cur, mock_file, "empty_table")
    mock_file.write.assert_not_called()


def test_dump_table_data_alembic_version_is_idempotent():
    service = BackupService()
    mock_cur = MagicMock()
    mock_cur.description = [("version_num",)]
    mock_cur.fetchall.return_value = [("045",)]
    mock_cur.mogrify.return_value = b"INSERT INTO alembic_version VALUES ('045');\n"
    mock_file = MagicMock()

    service._dump_table_data(mock_cur, mock_file, "alembic_version")

    assert "ON CONFLICT (version_num) DO NOTHING" in mock_cur.mogrify.call_args.args[0]


def test_sync_table_sequences_alembic_and_none(mocker):
    service = BackupService()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_file = MagicMock()
    service._sync_table_sequences(mock_cur, mock_file, ["alembic_version", "no_seq_table"])
    mock_file.write.assert_not_called()


def test_find_pg_dump_windows_glob(mocker):
    service = BackupService()
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("glob.glob", side_effect=[["C:\\Program Files\\PostgreSQL\\16\\bin\\pg_dump.exe"], []])
    found = service._find_pg_dump()
    assert found == "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_dump.exe"

    mocker.patch("glob.glob", return_value=[])
    assert service._find_pg_dump() is None


def test_filter_pg_dump_output(tmp_path):
    service = BackupService()
    out_file = str(tmp_path / "filtered.sql")
    raw = b"\\restrict foo\nSELECT 1;\n\\unrestrict bar\n"
    res = service._filter_pg_dump_output(raw, out_file)
    assert res is True
    with open(out_file, "r") as f:
        content = f.read()
    assert "\\restrict" not in content
    assert "\\unrestrict" not in content
    assert "SELECT 1;" in content


def test_dump_postgresql_schema_python_success_and_failure(mocker, tmp_path):
    service = BackupService()
    out_file = str(tmp_path / "schema.sql")
    res = service._dump_postgresql_schema_python(out_file)
    assert res is True

    mocker.patch("builtins.open", side_effect=OSError("Disk full"))
    res_fail = service._dump_postgresql_schema_python(out_file)
    assert res_fail is False


def test_dump_postgresql_schema_host_success(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value="/usr/bin/pg_dump")
    proc = MagicMock()
    proc.stdout = b"CREATE TABLE x();"
    mocker.patch("subprocess.run", return_value=proc)
    mocker.patch.object(service, "_filter_pg_dump_output", return_value=True)
    assert service._dump_postgresql_schema("schema.sql") is True


def test_dump_postgresql_schema_docker_fallback(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value="/usr/bin/pg_dump")
    mocker.patch("shutil.which", side_effect=lambda c: "/usr/bin/docker" if c == "docker" else None)
    proc = MagicMock()
    proc.stdout = b"CREATE TABLE x();"
    mocker.patch("subprocess.run", side_effect=[Exception("Host failed"), proc])
    mocker.patch.object(service, "_filter_pg_dump_output", return_value=True)
    assert service._dump_postgresql_schema("schema.sql") is True


def test_dump_postgresql_schema_python_fallback(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value=None)
    mocker.patch("shutil.which", return_value=None)
    mocker.patch.object(service, "_dump_postgresql_schema_python", return_value=True)
    assert service._dump_postgresql_schema("schema.sql") is True


def test_dump_postgresql_inserts_host_failure_docker_fallback(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value="/usr/bin/pg_dump")
    mocker.patch("shutil.which", side_effect=lambda c: "/usr/bin/docker" if c == "docker" else None)
    proc = MagicMock()
    proc.stdout = b"INSERT INTO x VALUES (1);"
    mocker.patch("subprocess.run", side_effect=[Exception("Host failed"), proc])
    mocker.patch.object(service, "_filter_pg_dump_output", return_value=True)
    assert service._dump_postgresql_inserts("inserts.sql") is True


def test_dump_postgresql_inserts_docker_failure_python_fallback(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value=None)
    mocker.patch("shutil.which", side_effect=lambda c: "/usr/bin/docker" if c == "docker" else None)
    mocker.patch("subprocess.run", side_effect=Exception("Docker failed"))
    mocker.patch.object(service, "_dump_postgresql_python", return_value=True)
    assert service._dump_postgresql_inserts("inserts.sql") is True


def test_find_pg_dump_shutil_which(mocker):
    service = BackupService()
    mocker.patch("shutil.which", return_value="/usr/bin/pg_dump")
    assert service._find_pg_dump() == "/usr/bin/pg_dump"


def test_dump_postgresql_schema_docker_failure(mocker):
    service = BackupService()
    mocker.patch.object(service, "_find_pg_dump", return_value=None)
    mocker.patch("shutil.which", side_effect=lambda c: "/usr/bin/docker" if c == "docker" else None)
    mocker.patch("subprocess.run", side_effect=Exception("Docker failed"))
    mocker.patch.object(service, "_dump_postgresql_schema_python", return_value=True)
    assert service._dump_postgresql_schema("schema.sql") is True


def test_create_safe_backup_cleanup_existing_on_failure(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_schema", return_value=False)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.getsize", return_value=0)
    mock_remove = mocker.patch("os.remove", side_effect=OSError("Remove error"))
    assert service.create_safe_backup() is None
    mock_remove.assert_called_once()


def test_create_safe_backup_cleanup_existing_on_exception(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_schema", side_effect=RuntimeError("Crash"))
    mocker.patch("os.path.exists", return_value=True)
    mock_remove = mocker.patch("os.remove", side_effect=OSError("Cannot remove"))
    assert service.create_safe_backup() is None
    mock_remove.assert_called_once()


def test_create_sql_dump_cleanup_existing_on_failure(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_inserts", return_value=False)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.getsize", return_value=0)
    mock_remove = mocker.patch("os.remove", side_effect=OSError("Remove error"))
    assert service.create_sql_dump() is None
    mock_remove.assert_called_once()


def test_create_sql_dump_cleanup_existing_on_exception(mocker):
    service = BackupService()
    mocker.patch.object(service, "_dump_postgresql_inserts", side_effect=RuntimeError("Crash"))
    mocker.patch("os.path.exists", return_value=True)
    mock_remove = mocker.patch("os.remove", side_effect=OSError("Cannot remove"))
    assert service.create_sql_dump() is None
    mock_remove.assert_called_once()


