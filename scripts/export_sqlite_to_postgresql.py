import argparse
import json
import math
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

try:
    from scripts.database_migration_config import (
        BOOLEAN_COLUMNS,
        DATE_COLUMNS,
        EXPECTED_COLUMNS,
        JSONB_COLUMNS,
        MIGRATION_TABLES,
        TABLE_ORDER,
        TIMESTAMPTZ_COLUMNS,
        TIME_COLUMNS,
        normalize_boolean,
        quote_identifier,
        sqlite_type_family,
    )
except ModuleNotFoundError:
    from database_migration_config import (
        BOOLEAN_COLUMNS,
        DATE_COLUMNS,
        EXPECTED_COLUMNS,
        JSONB_COLUMNS,
        MIGRATION_TABLES,
        TABLE_ORDER,
        TIMESTAMPTZ_COLUMNS,
        TIME_COLUMNS,
        normalize_boolean,
        quote_identifier,
        sqlite_type_family,
    )

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = ROOT_DIR / "spe.db"
DEFAULT_OUTPUT_SQL_PATH = ROOT_DIR / "scripts" / "data_inserts_postgresql.sql"


def get_timezone() -> str:
    configured = os.getenv("TIMEZONE")
    if configured:
        return configured
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TIMEZONE="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "America/Fortaleza"


def _escape_text(value: str) -> str:
    if "\x00" in value:
        raise ValueError("PostgreSQL não aceita byte NUL em campos de texto")
    return value.replace("'", "''")


def _format_timestamptz(value: object, timezone_name: str) -> str:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    timezone = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    else:
        parsed = parsed.astimezone(timezone)
    return f"'{_escape_text(parsed.isoformat())}'::timestamptz"


def _format_date(value: object) -> str:
    parsed = value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value).split()[0])
    return f"'{parsed.isoformat()}'::date"


def _format_time(value: object) -> str:
    parsed = value if isinstance(value, time) else time.fromisoformat(str(value))
    return f"'{parsed.isoformat()}'::time"


def format_cell(
    table_name: str,
    col_name: str,
    value: object,
    declared_type: str = "",
    timezone_name: str | None = None,
) -> str:
    if value is None:
        return "NULL"

    if col_name in BOOLEAN_COLUMNS.get(table_name, set()):
        return "TRUE" if normalize_boolean(value) else "FALSE"

    if col_name in JSONB_COLUMNS.get(table_name, set()):
        parsed = value if isinstance(value, (dict, list)) else json.loads(str(value))
        serialized = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        return f"'{_escape_text(serialized)}'::jsonb"

    if col_name in TIMESTAMPTZ_COLUMNS.get(table_name, set()):
        return _format_timestamptz(value, timezone_name or get_timezone())

    if col_name in DATE_COLUMNS.get(table_name, set()):
        return _format_date(value)

    if col_name in TIME_COLUMNS.get(table_name, set()):
        return _format_time(value)

    family = sqlite_type_family(declared_type)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"número não finito em {table_name}.{col_name}: {value!r}")
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        if family != "binary":
            raise ValueError(f"valor binário inesperado em {table_name}.{col_name}")
        return f"decode('{bytes(value).hex()}', 'hex')"

    return f"'{_escape_text(str(value))}'"


def _sqlite_schema(cursor: sqlite3.Cursor) -> dict[str, dict[str, str]]:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    table_names = {row[0] for row in cursor.fetchall()}
    expected_tables = set(MIGRATION_TABLES)
    missing_tables = sorted(expected_tables - table_names)
    extra_tables = sorted(table_names - expected_tables)
    if missing_tables or extra_tables:
        details = []
        if missing_tables:
            details.append(f"tabelas ausentes: {', '.join(missing_tables)}")
        if extra_tables:
            details.append(f"tabelas não suportadas: {', '.join(extra_tables)}")
        raise ValueError("Schema SQLite incompatível (" + "; ".join(details) + ")")

    schema: dict[str, dict[str, str]] = {}
    for table_name in MIGRATION_TABLES:
        cursor.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
        columns = {str(row[1]): str(row[2] or "") for row in cursor.fetchall()}
        expected_columns = EXPECTED_COLUMNS[table_name]
        if set(columns) != expected_columns:
            missing = sorted(expected_columns - set(columns))
            extra = sorted(set(columns) - expected_columns)
            details = []
            if missing:
                details.append(f"ausentes: {', '.join(missing)}")
            if extra:
                details.append(f"extras: {', '.join(extra)}")
            raise ValueError(f"Colunas incompatíveis em {table_name} ({'; '.join(details)})")
        schema[table_name] = columns
    return schema


def _export_table_data(
    out: TextIO,
    table_name: str,
    rows: list[sqlite3.Row],
    column_types: dict[str, str],
    batch_size: int,
    timezone_name: str,
) -> None:
    if not rows:
        return

    columns = list(rows[0].keys())
    columns_sql = ", ".join(quote_identifier(column) for column in columns)
    table_sql = quote_identifier(table_name)

    for offset in range(0, len(rows), batch_size):
        batch = rows[offset: offset + batch_size]
        values = []
        for row in batch:
            formatted = [
                format_cell(
                    table_name,
                    column,
                    row[column],
                    column_types[column],
                    timezone_name,
                )
                for column in columns
            ]
            values.append("(" + ", ".join(formatted) + ")")
        out.write(
            f"INSERT INTO {table_sql} ({columns_sql}) VALUES\n  "
            + ",\n  ".join(values)
            + ";\n"
        )
    out.write("\n")


def _write_dump(
    output: TextIO,
    cursor: sqlite3.Cursor,
    schema: dict[str, dict[str, str]],
    batch_size: int,
    timezone_name: str,
) -> dict[str, int]:
    stats: dict[str, int] = {}
    for table_name in TABLE_ORDER:
        table_sql = quote_identifier(table_name)
        cursor.execute(f"SELECT * FROM {table_sql} ORDER BY {quote_identifier('id')} ASC")
        rows = cursor.fetchall()
        stats[table_name] = len(rows)
        _export_table_data(
            output,
            table_name,
            rows,
            schema[table_name],
            batch_size,
            timezone_name,
        )

    for table_name in TABLE_ORDER:
        table_literal = table_name.replace("'", "''")
        table_sql = quote_identifier(table_name)
        output.write(
            "SELECT setval(pg_get_serial_sequence("
            f"'{table_literal}', 'id'), COALESCE((SELECT MAX(id) FROM {table_sql}), 1), "
            f"EXISTS (SELECT 1 FROM {table_sql}));\n"
        )
    return stats


def export_sqlite_to_postgresql(
    sqlite_path: Path,
    output_sql_path: Path,
    batch_size: int = 100,
) -> dict[str, int]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"Arquivo SQLite não encontrado: {sqlite_path}")
    if batch_size < 1:
        raise ValueError("batch_size deve ser maior que zero")

    timezone_name = get_timezone()
    ZoneInfo(timezone_name)
    output_sql_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(f"file:{sqlite_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    temp_path: Path | None = None
    try:
        cursor = connection.cursor()
        cursor.execute("BEGIN")
        schema = _sqlite_schema(cursor)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output_sql_path.name}.",
            suffix=".tmp",
            dir=output_sql_path.parent,
            delete=False,
        ) as output:
            temp_path = Path(output.name)
            stats = _write_dump(output, cursor, schema, batch_size, timezone_name)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, output_sql_path)
        temp_path = None
        return stats
    finally:
        connection.close()
        if temp_path and temp_path.exists():
            temp_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta somente os dados do SQLite para SQL compatível com PostgreSQL."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_SQLITE_PATH, help="Arquivo SQLite de origem")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_SQL_PATH, help="SQL de saída")
    parser.add_argument("--batch-size", type=int, default=100, help="Linhas por INSERT (padrão: 100)")
    args = parser.parse_args()

    try:
        stats = export_sqlite_to_postgresql(args.db, args.out, args.batch_size)
        print(f"Dump de dados gerado com sucesso: {args.out}")
        for table, count in stats.items():
            print(f"  - {table}: {count} linhas")
    except Exception as exc:
        print(f"Erro na exportação: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
