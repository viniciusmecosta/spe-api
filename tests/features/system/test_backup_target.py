from types import SimpleNamespace

import pytest

from app.features.system.backup_service import BackupService
from scripts import db_manager


PARAMS = {
    "host": "external-db",
    "port": 55439,
    "user": "synthetic",
    "password": "synthetic-only",
    "dbname": "configured-db",
}


@pytest.mark.parametrize(
    "method", ["_dump_postgresql_schema", "_dump_postgresql_inserts"]
)
def test_failed_native_dump_never_switches_to_a_named_container(
    method, mocker, tmp_path
):
    service = BackupService()
    mocker.patch.object(service, "_get_postgres_connection_params", return_value=PARAMS)
    mocker.patch.object(service, "_find_pg_dump", return_value="/native/pg_dump")
    mocker.patch("shutil.which", return_value="/usr/bin/docker")
    python_dump = mocker.patch.object(
        service, "_dump_postgresql_python", return_value=True
    )
    run = mocker.patch(
        "subprocess.run",
        side_effect=[
            RuntimeError("native dump failed"),
            SimpleNamespace(stdout=b"INSERT INTO unrelated_database VALUES (1);"),
        ],
    )
    mocker.patch.object(service, "_filter_pg_dump_output", return_value=True)

    result = getattr(service, method)(str(tmp_path / "data.sql"))

    assert run.call_count == 1
    command = run.call_args.args[0]
    assert command[0] == "/native/pg_dump"
    assert command[command.index("-h") + 1] == PARAMS["host"]
    assert command[command.index("-p") + 1] == str(PARAMS["port"])
    assert command[command.index("-d") + 1] == PARAMS["dbname"]
    if method == "_dump_postgresql_inserts":
        assert result is True
        python_dump.assert_called_once_with(str(tmp_path / "data.sql"), PARAMS)
    else:
        assert result is False
        python_dump.assert_not_called()


def test_snapshot_without_native_client_fails_without_running_docker(mocker, tmp_path):
    service = BackupService()
    service._snapshot_id = "synthetic-snapshot"
    mocker.patch.object(service, "_get_postgres_connection_params", return_value=PARAMS)
    mocker.patch.object(service, "_find_pg_dump", return_value=None)
    mocker.patch("shutil.which", return_value="/usr/bin/docker")
    run = mocker.patch(
        "subprocess.run", return_value=SimpleNamespace(returncode=1, stderr=b"")
    )

    assert (
        service._dump_with_snapshot(str(tmp_path / "data.sql"), schema_only=False)
        is False
    )
    run.assert_not_called()


@pytest.mark.parametrize("operation", ["dump_schema_ddl", "dump_data_inserts"])
def test_cli_without_native_client_keeps_the_configured_target(
    operation, mocker, tmp_path
):
    mocker.patch.object(db_manager, "get_pg_credentials", return_value=PARAMS)
    mocker.patch.object(db_manager, "find_pg_binary", return_value=None)
    mocker.patch("shutil.which", return_value="/usr/bin/docker")
    run = mocker.patch(
        "subprocess.run", return_value=SimpleNamespace(returncode=1, stderr=b"")
    )
    introspect = mocker.patch.object(
        db_manager,
        "extract_live_ddl_from_postgres",
        return_value="CREATE TABLE synthetic(id int);",
    )
    mocker.patch.object(db_manager, "_database_counts", return_value={})
    mocker.patch.object(db_manager, "add_manifest")
    from app.features.system.backup_service import backup_service

    mocker.patch.object(
        backup_service, "_get_postgres_connection_params", return_value=PARAMS
    )
    python_dump = mocker.patch.object(
        backup_service,
        "_dump_postgresql_python",
        side_effect=lambda path, params: tmp_path.joinpath("data.sql").write_text(
            "SELECT 1;"
        ),
    )

    getattr(db_manager, operation)(tmp_path / "data.sql")

    run.assert_not_called()
    if operation == "dump_data_inserts":
        python_dump.assert_called_once_with(str(tmp_path / "data.sql"), PARAMS)
    else:
        introspect.assert_called_once_with(include_alembic_version=True)
