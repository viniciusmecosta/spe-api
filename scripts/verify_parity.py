import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import date, datetime
from datetime import time as dtime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from app.database.connection import postgres_connection_params

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    from scripts.database_migration_config import (
        BOOLEAN_COLUMNS,
        JSONB_COLUMNS,
        MIGRATION_TABLES,
        TABLE_ORDER,
        are_type_families_compatible,
        normalize_boolean,
        postgres_type_family,
        quote_identifier,
        sqlite_type_family,
    )
except ModuleNotFoundError:
    from database_migration_config import (
        BOOLEAN_COLUMNS,
        JSONB_COLUMNS,
        MIGRATION_TABLES,
        TABLE_ORDER,
        are_type_families_compatible,
        normalize_boolean,
        postgres_type_family,
        quote_identifier,
        sqlite_type_family,
    )

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = ROOT_DIR / "spe.db"

def load_environment() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists() and load_dotenv:
        load_dotenv(dotenv_path=env_path, override=False)


def get_pg_credentials() -> dict[str, str]:
    load_environment()
    return {
        key: str(value) for key, value in postgres_connection_params(
            os.getenv("SQLALCHEMY_DATABASE_URI", ""), os.environ,
        ).items()
    }


def get_timezone() -> str:
    load_environment()
    return os.getenv("TIMEZONE", "America/Fortaleza")


def connect_with_retry(creds: dict[str, str], max_retries: int = 30, delay: float = 1.0) -> Any:
    if psycopg2 is None:
        raise RuntimeError("Driver psycopg2 não está instalado.")

    for attempt in range(1, max_retries + 1):
        try:
            return psycopg2.connect(
                host=creds["host"],
                port=int(creds["port"]),
                user=creds["user"],
                password=creds["password"],
                dbname=creds["dbname"],
                connect_timeout=5,
            )
        except psycopg2.OperationalError as e:
            if attempt == max_retries:
                raise RuntimeError(f"Não foi possível conectar ao PostgreSQL: {e}") from e
            time.sleep(delay)


def parse_jsonb_value(val: Any) -> Any:
    if val in (None, "null"):
        return None
    if isinstance(val, str):
        return json.loads(val)
    return val


def _compare_datetime(sq_val: Any, pg_val: datetime, tz: ZoneInfo) -> bool:
    if isinstance(sq_val, str):
        dt_s = datetime.fromisoformat(sq_val)
        dt_s = dt_s.replace(tzinfo=tz) if dt_s.tzinfo is None else dt_s.astimezone(tz)
        dt_p = pg_val.astimezone(tz) if pg_val.tzinfo is not None else pg_val.replace(tzinfo=tz)
        return dt_s == dt_p
    if isinstance(sq_val, datetime):
        dt_s = sq_val.astimezone(tz) if sq_val.tzinfo is not None else sq_val.replace(tzinfo=tz)
        dt_p = pg_val.astimezone(tz) if pg_val.tzinfo is not None else pg_val.replace(tzinfo=tz)
        return dt_s == dt_p
    return False


def _compare_date(sq_val: Any, pg_val: date) -> bool:
    if isinstance(sq_val, str):
        return date.fromisoformat(sq_val.split()[0]) == pg_val
    if isinstance(sq_val, date):
        return sq_val == pg_val
    return False


def _compare_time(sq_val: Any, pg_val: dtime) -> bool:
    if isinstance(sq_val, str):
        return dtime.fromisoformat(sq_val) == pg_val
    if isinstance(sq_val, dtime):
        return sq_val == pg_val
    return False


def _compare_numeric(sq_val: Any, pg_val: Any) -> bool | None:
    numeric_types = (int, float, Decimal)
    if isinstance(pg_val, numeric_types) and isinstance(sq_val, numeric_types):
        try:
            return abs(Decimal(str(sq_val)) - Decimal(str(pg_val))) <= Decimal("0.00001")
        except (ValueError, TypeError):
            return None
    return None


def are_cells_equal(sq_val: Any, pg_val: Any, col_name: str, table_name: str, tz: ZoneInfo) -> bool:
    if table_name in JSONB_COLUMNS and col_name in JSONB_COLUMNS[table_name]:
        return parse_jsonb_value(sq_val) == parse_jsonb_value(pg_val)

    if sq_val is None and pg_val is None:
        return True
    if sq_val is None or pg_val is None:
        return False

    if table_name in BOOLEAN_COLUMNS and col_name in BOOLEAN_COLUMNS[table_name]:
        try:
            return normalize_boolean(sq_val) == normalize_boolean(pg_val)
        except ValueError:
            return False

    if isinstance(pg_val, datetime):
        return _compare_datetime(sq_val, pg_val, tz)

    if isinstance(pg_val, date) and not isinstance(pg_val, datetime):
        return _compare_date(sq_val, pg_val)

    if isinstance(pg_val, dtime):
        return _compare_time(sq_val, pg_val)

    numeric_res = _compare_numeric(sq_val, pg_val)
    if numeric_res is not None:
        return numeric_res

    return str(sq_val) == str(pg_val)


def _compare_table_rows(
    table: str,
    sq_rows: list,
    pg_rows: list,
    common_cols: list[str],
    target_tz: ZoneInfo,
) -> int:
    table_diffs = 0
    for sq_r, pg_r in zip(sq_rows, pg_rows):
        table_diffs += _compare_row(
            table, sq_r, pg_r, common_cols, target_tz, table_diffs
        )
    return table_diffs


def _compare_row(table: str, sqlite_row: tuple, postgres_row: tuple,
                 columns: list[str], target_tz: ZoneInfo, prior_diffs: int) -> int:
    row_diffs = 0
    for column_index, column in enumerate(columns):
        if are_cells_equal(
            sqlite_row[column_index], postgres_row[column_index],
            column, table, target_tz,
        ):
            continue
        row_diffs += 1
        if prior_diffs + row_diffs <= 3:
            _log_cell_difference(table, sqlite_row, postgres_row, column_index, column)
    return row_diffs


def _log_cell_difference(table: str, sqlite_row, postgres_row, column_index: int,
                         column: str) -> None:
    sqlite_value, postgres_value = sqlite_row[column_index], postgres_row[column_index]
    if table == "user_biometrics" and column == "template_data":
        sqlite_value = f"<biometria: {len(str(sqlite_value))} caracteres>"
        postgres_value = f"<biometria: {len(str(postgres_value))} caracteres>"
    else:
        sqlite_value, postgres_value = repr(sqlite_value), repr(postgres_value)
    print(
        f"  [DIVERGÊNCIA] {table} (ID {sqlite_row[0]}), coluna '{column}': "
        f"SQLite={sqlite_value} vs PG={postgres_value}"
    )


def get_table_schema(
    table: str,
    sq_cur: Any,
    pg_cur: Any,
) -> tuple[list[str], list[str], list[str]]:
    sq_cur.execute(f"PRAGMA table_info({quote_identifier(table)})")
    sq_info = [(str(row[1]), str(row[2] or "")) for row in sq_cur.fetchall()]

    pg_cur.execute(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    pg_info = [(str(row[0]), str(row[1]), str(row[2])) for row in pg_cur.fetchall()]
    sq_cols = [column for column, _ in sq_info]
    pg_cols = [column for column, _, _ in pg_info]
    schema_errors: list[str] = []

    schema_errors = _column_set_errors(sq_cols, pg_cols)
    if schema_errors:
        return sq_cols, pg_cols, schema_errors

    sq_types = {column: sqlite_type_family(declared) for column, declared in sq_info}
    pg_types = {
        column: postgres_type_family(data_type, udt_name)
        for column, data_type, udt_name in pg_info
    }
    for column in sq_cols:
        if not are_type_families_compatible(sq_types[column], pg_types[column]):
            schema_errors.append(
                f"{column}: SQLite={sq_types[column]} PostgreSQL={pg_types[column]}"
            )
    return sq_cols, pg_cols, schema_errors


def _column_set_errors(sqlite_columns: list[str], postgres_columns: list[str]) -> list[str]:
    missing = sorted(set(sqlite_columns) - set(postgres_columns))
    extra = sorted(set(postgres_columns) - set(sqlite_columns))
    errors = []
    if missing:
        errors.append("ausentes no PostgreSQL: " + ", ".join(missing))
    if extra:
        errors.append("extras no PostgreSQL: " + ", ".join(extra))
    return errors


def _report_row_id_differences(table: str, sqlite_ids: set, postgres_ids: set) -> int:
    missing_ids = sorted(sqlite_ids - postgres_ids)
    extra_ids = sorted(postgres_ids - sqlite_ids)
    if missing_ids:
        print(f"  [AUSENTES NO PG] {table}: {missing_ids[:10]}")
    if extra_ids:
        print(f"  [EXTRAS NO PG] {table}: {extra_ids[:10]}")
    return len(missing_ids) + len(extra_ids)


def verify_table_data(
    table: str,
    sq_cur: Any,
    pg_cur: Any,
    common_cols: list[str],
    target_tz: ZoneInfo,
) -> tuple[bool, int, int, int]:
    cols_sql = ", ".join(quote_identifier(column) for column in common_cols)
    table_sql = quote_identifier(table)
    sq_cur.execute(f"SELECT {cols_sql} FROM {table_sql} ORDER BY {quote_identifier('id')}")
    pg_cur.execute(f"SELECT {cols_sql} FROM {table_sql} ORDER BY {quote_identifier('id')}")

    sq_rows = sq_cur.fetchall()
    pg_rows = pg_cur.fetchall()

    if table == "audit_logs":
        action_index = common_cols.index("action")
        sq_rows = [
            (new_id, *row[1:])
            for new_id, row in enumerate(
                (row for row in sq_rows if row[action_index] != "LOGIN"), 1
            )
        ]

    sq_count = len(sq_rows)
    pg_count = len(pg_rows)

    sq_ids = {row[0] for row in sq_rows}
    pg_ids = {row[0] for row in pg_rows}
    if sq_ids != pg_ids:
        diffs = _report_row_id_differences(table, sq_ids, pg_ids)
        return False, sq_count, pg_count, diffs

    diffs = _compare_table_rows(table, sq_rows, pg_rows, common_cols, target_tz)
    return diffs == 0, sq_count, pg_count, diffs


def verify_single_table(
    table: str,
    sq_cur: Any,
    pg_cur: Any,
    target_tz: ZoneInfo,
) -> tuple[bool, int, int, int]:
    sq_cols, pg_cols, schema_errors = get_table_schema(table, sq_cur, pg_cur)

    if not sq_cols or not pg_cols or schema_errors:
        _print_schema_failure(table, schema_errors)
        return False, 0, 0, max(1, len(schema_errors))

    matched, sq_count, pg_count, diffs = verify_table_data(table, sq_cur, pg_cur, sq_cols, target_tz)
    status_str = "[OK]" if matched else f"[{diffs} ERROS]"
    print(f"{table:28} | {sq_count:>7} | {pg_count:>8} | {diffs:>12} | {status_str:^12}")

    return matched, sq_count, pg_count, diffs


def _print_schema_failure(table: str, errors: list[str]) -> None:
    print(f"{table:28} | {'N/A':>7} | {'N/A':>8} | {'N/A':>12} | {'ERRO DE SCHEMA':^12}")
    for error in errors[:5]:
        print(f"  [SCHEMA] {error}")


def _verify_tables(sq_cur, pg_cur, target_tz: ZoneInfo) -> tuple[bool, int, int, int]:
    all_matched = True
    total_sq_rows = total_pg_rows = total_diffs = 0
    for table in TABLE_ORDER:
        matched, sqlite_count, postgres_count, differences = verify_single_table(
            table, sq_cur, pg_cur, target_tz
        )
        total_sq_rows += sqlite_count
        total_pg_rows += postgres_count
        total_diffs += differences
        if not matched:
            all_matched = False
    return all_matched, total_sq_rows, total_pg_rows, total_diffs


def _print_audit_totals(all_matched: bool, sqlite_rows: int,
                        postgres_rows: int, differences: int) -> None:
    print("-" * 75)
    print(f"Total de registros: SQLite={sqlite_rows:,} | PostgreSQL={postgres_rows:,}")
    print(f"Total de divergências detectadas: {differences}")
    status = "100% IDÊNTICO E AUDITADO COM SUCESSO" if all_matched else "DIVERGÊNCIAS DETECTADAS"
    print(f"Resultado Final: {status}")
    print("=" * 75)


def _print_table_set_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"[SCHEMA] {error}")


def _run_parity_checks(sq_cur: Any, pg_cur: Any, target_tz: ZoneInfo) -> bool:
    table_errors = validate_table_sets(sq_cur, pg_cur)
    if table_errors:
        _print_table_set_errors(table_errors)
        return False

    all_matched, sqlite_rows, postgres_rows, differences = _verify_tables(
        sq_cur, pg_cur, target_tz
    )
    _print_audit_totals(all_matched, sqlite_rows, postgres_rows, differences)
    return all_matched


def validate_table_sets(sq_cur: Any, pg_cur: Any) -> list[str]:
    sq_cur.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    sqlite_tables = {row[0] for row in sq_cur.fetchall()}
    pg_cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    postgres_tables = {row[0] for row in pg_cur.fetchall()}
    expected = set(MIGRATION_TABLES)
    errors = []
    for label, actual in (("SQLite", sqlite_tables), ("PostgreSQL", postgres_tables)):
        missing = sorted(expected - actual)
        allowed_extra = {"daily_summaries", "background_jobs"} if label == "PostgreSQL" else set()
        extra = sorted(actual - expected - allowed_extra)
        if missing:
            errors.append(f"{label}: tabelas ausentes: {', '.join(missing)}")
        if extra:
            errors.append(f"{label}: tabelas extras: {', '.join(extra)}")
    return errors


def verify_parity(sqlite_path: Path = DEFAULT_SQLITE_PATH) -> bool:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Arquivo SQLite não encontrado: {sqlite_path}")

    creds = get_pg_credentials()
    tz_name = get_timezone()
    target_tz = ZoneInfo(tz_name)

    sq_conn = sqlite3.connect(sqlite_path)
    sq_cur = sq_conn.cursor()
    sq_cur.execute("BEGIN")

    pg_conn = connect_with_retry(creds)
    pg_cur = pg_conn.cursor()
    pg_cur.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

    print("=" * 75)
    print("AUDITORIA DE PARIDADE CÉLULA A CÉLULA (SQLite <-> PostgreSQL)")
    print(f"Base SQLite: {sqlite_path.name} | Fuso Horário: {tz_name}")
    print("=" * 75)
    print(f"{'Tabela':28} | {'SQLite':>7} | {'PG':>8} | {'Divergências':>12} | {'Status':^12}")
    print("-" * 75)

    try:
        return _run_parity_checks(sq_cur, pg_cur, target_tz)
    finally:
        sq_cur.close()
        sq_conn.close()
        pg_cur.close()
        pg_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verifica paridade célula a célula entre o banco SQLite e o PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="Caminho do arquivo SQLite (padrão: spe.db)",
    )

    args = parser.parse_args()

    try:
        success = verify_parity(args.sqlite_db)
        sys.exit(0 if success else 1)
    except Exception as e:
        logging.getLogger(__name__).exception("Falha na operação", exc_info=False)
        print(f"Erro na auditoria: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
