from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts import apply_sql_to_postgresql, db_manager


def test_identifier_quoting_escapes_embedded_quotes():
    assert apply_sql_to_postgresql.quote_identifier('weird"name') == '"weird""name"'


def test_restore_discovers_backup_without_sqlite_migration_default(monkeypatch, mocker):
    monkeypatch.setattr('sys.argv', ['restore', '--restore', '--yes'])
    restore = mocker.patch.object(apply_sql_to_postgresql, 'restore_backup', return_value={
        'database': 'spe_test', 'statements': 1, 'insert_tables': ['users'],
    })
    apply_sql_to_postgresql.main()
    restore.assert_called_once_with(None, allow_destructive=True, expected_database=None, dry_run=False, allow_unverified_dump=False)


def test_restore_requires_explicit_source_or_discovery(monkeypatch):
    monkeypatch.setattr('sys.argv', ['restore', '--yes'])
    with pytest.raises(SystemExit) as error:
        apply_sql_to_postgresql.main()
    assert error.value.code == 2


def test_explicit_postgres_dump_is_validated_without_mutation(monkeypatch, mocker):
    monkeypatch.setattr('sys.argv', ['restore', '--file', 'backup.sql', '--dry-run'])
    apply = mocker.patch.object(apply_sql_to_postgresql, 'apply_sql_file', return_value={
        'database': 'spe_test', 'statements': 1, 'insert_tables': ['users'],
    })
    apply_sql_to_postgresql.main()
    apply.assert_called_once_with(Path('backup.sql'), truncate_first=True, allow_destructive=False, expected_database=None, dry_run=True, allow_unverified_dump=False)


def test_db_manager_keeps_postgres_dump_and_restore(monkeypatch, mocker):
    monkeypatch.setattr('sys.argv', ['db_manager', '--dump', '--dump-ddl', '--dump-data', '--restore', '--yes', '--file', 'backup.zip.enc', '--confirm-database', 'spe_test'])
    dump = mocker.patch.object(db_manager, 'dump_database')
    ddl = mocker.patch.object(db_manager, 'dump_schema_ddl')
    data = mocker.patch.object(db_manager, 'dump_data_inserts')
    restore = mocker.patch.object(db_manager, 'restore_database')
    db_manager.main()
    dump.assert_called_once_with()
    ddl.assert_called_once_with()
    data.assert_called_once_with()
    restore.assert_called_once_with(Path('backup.zip.enc'), expected_database='spe_test')


def test_db_manager_without_operation_shows_help(monkeypatch, mocker, capsys):
    monkeypatch.setattr('sys.argv', ['db_manager'])
    dump = mocker.patch.object(db_manager, 'dump_database')
    with pytest.raises(SystemExit) as error:
        db_manager.main()
    assert error.value.code == 0
    assert '--dump' in capsys.readouterr().out
    dump.assert_not_called()


def test_db_manager_rejects_restore_without_confirmation(monkeypatch, mocker):
    monkeypatch.setattr('sys.argv', ['db_manager', '--restore'])
    restore = mocker.patch.object(db_manager, 'restore_database', new=MagicMock())
    with pytest.raises(SystemExit) as error:
        db_manager.main()
    assert error.value.code == 1
    restore.assert_not_called()


@pytest.mark.parametrize('option', ['--export-sqlite', '--sqlite-db', '--verify', '--apply-dump'])
def test_db_manager_rejects_removed_migration_options(monkeypatch, option):
    monkeypatch.setattr('sys.argv', ['db_manager', option])
    with pytest.raises(SystemExit) as error:
        db_manager.main()
    assert error.value.code == 2


def test_zip_with_duplicate_preferred_dump_is_rejected(tmp_path):
    from zipfile import ZipFile

    path = tmp_path / 'backup.zip'
    with ZipFile(path, 'w') as archive:
        archive.writestr('first/data.sql', 'INSERT INTO users VALUES (1);')
        archive.writestr('second/data.sql', 'INSERT INTO users VALUES (2);')
    with ZipFile(path) as archive, pytest.raises(ValueError, match='duplicados'):
        apply_sql_to_postgresql._find_data_member(archive)


def test_zip_with_unambiguous_preferred_dump_keeps_existing_selection(tmp_path):
    from zipfile import ZipFile

    path = tmp_path / 'backup.zip'
    with ZipFile(path, 'w') as archive:
        archive.writestr('backup/data.sql', 'INSERT INTO users VALUES (1);')
        archive.writestr('schema.sql', 'CREATE TABLE users (id integer);')
    with ZipFile(path) as archive:
        member = apply_sql_to_postgresql._find_data_member(archive)
        assert member.filename == 'backup/data.sql'


def test_zip_with_single_unrecognized_sql_dump_is_supported(tmp_path):
    from zipfile import ZipFile

    path = tmp_path / 'backup.zip'
    with ZipFile(path, 'w') as archive:
        archive.writestr('legacy/custom.sql', 'INSERT INTO users VALUES (1);')
    with ZipFile(path) as archive:
        member = apply_sql_to_postgresql._find_data_member(archive)
        assert member.filename == 'legacy/custom.sql'


def test_zip_without_unambiguous_sql_is_rejected(tmp_path):
    from zipfile import ZipFile

    path = tmp_path / 'backup.zip'
    with ZipFile(path, 'w') as archive:
        archive.writestr('first.sql', 'INSERT INTO users VALUES (1);')
        archive.writestr('second.sql', 'INSERT INTO users VALUES (2);')
    with ZipFile(path) as archive, pytest.raises(FileNotFoundError, match='inequívoco'):
        apply_sql_to_postgresql._find_data_member(archive)
