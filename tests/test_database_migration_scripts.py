import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.apply_sql_to_postgresql import (
    extract_dump_alembic_revisions,
    _validate_target_schema,
    prepare_data_statements,
    split_sql_statements,
    strip_sql_comments,
)
from scripts.database_migration_config import (
    BOOLEAN_COLUMNS,
    DATE_COLUMNS,
    EXPECTED_COLUMNS,
    JSONB_COLUMNS,
    MIGRATION_TABLES,
    TIMESTAMPTZ_COLUMNS,
    TIME_COLUMNS,
    are_type_families_compatible,
    normalize_boolean,
    postgres_type_family,
    sqlite_type_family,
)
from scripts.export_sqlite_to_postgresql import export_sqlite_to_postgresql, format_cell


def _declared_type(table: str, column: str) -> str:
    if column in BOOLEAN_COLUMNS.get(table, set()):
        return "BOOLEAN"
    if column in JSONB_COLUMNS.get(table, set()):
        return "JSON"
    if column in TIMESTAMPTZ_COLUMNS.get(table, set()):
        return "DATETIME"
    if column in DATE_COLUMNS.get(table, set()):
        return "DATE"
    if column in TIME_COLUMNS.get(table, set()):
        return "TIME"
    if column == "id" or column.endswith("_id"):
        return "INTEGER"
    return "VARCHAR"


def _create_compatible_sqlite(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        for table in MIGRATION_TABLES:
            columns = EXPECTED_COLUMNS[table]
            definitions = [
                f'"{column}" {_declared_type(table, column)}'
                for column in sorted(columns, key=lambda name: (name != "id", name))
            ]
            connection.execute(f'CREATE TABLE "{table}" ({", ".join(definitions)})')
        connection.execute("INSERT INTO alembic_version (version_num) VALUES ('045')")
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, True), (0, False), ("true", True), ("FALSE", False), ("yes", True), ("n", False)],
)
def test_normalize_boolean_accepts_known_values(value, expected):
    assert normalize_boolean(value) is expected


def test_normalize_boolean_rejects_unknown_value():
    with pytest.raises(ValueError, match="booleano inválido"):
        normalize_boolean(2)


def test_format_cell_converts_semantic_types_strictly():
    assert format_cell("users", "is_active", "1", "BOOLEAN") == "TRUE"
    assert format_cell("users", "created_at", "2026-01-02 03:04:05", "DATETIME", "America/Fortaleza") == (
        "'2026-01-02T03:04:05-03:00'::timestamptz"
    )
    assert format_cell("audit_logs", "new_data", '{"á": 1}', "JSON") == "'{\"á\":1}'::jsonb"
    with pytest.raises(ValueError, match="booleano inválido"):
        format_cell("users", "is_active", "talvez", "BOOLEAN")
    with pytest.raises(ValueError, match="byte NUL"):
        format_cell("users", "name", "a\x00b", "VARCHAR")


def test_sql_splitter_preserves_semicolon_inside_literals():
    statements = split_sql_statements(
        "-- header\nINSERT INTO users (id, name) VALUES (1, 'a;b'); /* x;y */ COMMIT;"
    )
    assert len(statements) == 2
    assert "'a;b'" in statements[0]


def test_prepare_data_statements_strips_transactions_and_alembic_metadata():
    statements, tables = prepare_data_statements(
        """
        BEGIN;
        INSERT INTO alembic_version (version_num) VALUES ('old');
        INSERT INTO public.users (id, name) VALUES (1, 'A');
        SELECT pg_catalog.setval('public.users_id_seq', 1, true);
        COMMIT;
        """
    )
    assert tables == {"users"}
    assert len(statements) == 2
    assert all("alembic_version" not in statement for statement in statements)
    assert extract_dump_alembic_revisions(
        "INSERT INTO public.alembic_version (version_num) VALUES ('001');"
    ) == {"001"}


def test_strip_sql_comments_preserves_comment_markers_inside_data():
    sql = "-- comentário\nINSERT INTO t VALUES ('-- dado', '/* dado */'); /* fim */\n"
    cleaned = strip_sql_comments(sql)
    assert "comentário" not in cleaned
    assert "fim" not in cleaned
    assert "'-- dado'" in cleaned
    assert "'/* dado */'" in cleaned


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users;",
        "DELETE FROM users;",
        "UPDATE users SET name = 'x';",
        "COPY users FROM STDIN;",
        "INSERT INTO private.users (id) VALUES (1);",
        r"\i /tmp/other.sql",
    ],
)
def test_prepare_data_statements_rejects_non_data_dump_commands(sql):
    with pytest.raises(ValueError):
        prepare_data_statements(sql)


def test_export_is_data_only_atomic_and_adds_explicit_timezone(tmp_path):
    sqlite_path = tmp_path / "source.db"
    output_path = tmp_path / "out" / "data.sql"
    _create_compatible_sqlite(sqlite_path)
    connection = sqlite3.connect(sqlite_path)
    try:
        connection.execute(
            """
            INSERT INTO companies
                (id, name, cnpj, address, auto_print_receipt)
            VALUES (1, 'Empresa', '1', 'Rua', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO users
                (id, username, name, is_active, created_at)
            VALUES (1, 'user', 'Usuário', 1, '2026-01-02 03:04:05')
            """
        )
        connection.commit()
    finally:
        connection.close()

    stats = export_sqlite_to_postgresql(sqlite_path, output_path, batch_size=1)
    sql = output_path.read_text(encoding="utf-8")
    assert stats["companies"] == 1
    assert stats["users"] == 1
    assert "CREATE TABLE" not in sql
    assert "alembic_version" not in sql
    assert "'2026-01-02T03:04:05-03:00'::timestamptz" in sql
    assert "EXISTS (SELECT 1 FROM \"printers\")" in sql

    output_path.write_text("known-good", encoding="utf-8")
    connection = sqlite3.connect(sqlite_path)
    try:
        connection.execute("UPDATE users SET is_active = 7")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ValueError, match="booleano inválido"):
        export_sqlite_to_postgresql(sqlite_path, output_path)
    assert output_path.read_text(encoding="utf-8") == "known-good"


def test_type_family_compatibility_covers_sqlite_to_postgres_differences():
    assert sqlite_type_family("VARCHAR(8)") == "text"
    assert sqlite_type_family("DATETIME") == "datetime"
    assert postgres_type_family("USER-DEFINED", "recordtype") == "enum"
    assert are_type_families_compatible("text", "enum")
    assert not are_type_families_compatible("text", "datetime")


def test_target_schema_requires_matching_backup_alembic_revision():
    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        [("alembic_version",), ("users",)],
        [("001",)],
    ]
    with pytest.raises(RuntimeError, match="não corresponde"):
        _validate_target_schema(cursor, {"users"}, {"999"})
