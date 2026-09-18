import argparse
import json
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
    uri = os.getenv("SQLALCHEMY_DATABASE_URI", "")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    dbname = os.getenv("POSTGRES_DB")

    if uri and (not host or not user or not dbname):
        try:
            from sqlalchemy.engine import make_url

            parsed = make_url(uri)
            host = host or parsed.host
            port = port or (str(parsed.port) if parsed.port else None)
            user = user or parsed.username
            password = password if password is not None else parsed.password
            dbname = dbname or parsed.database
        except Exception:
            pass

    return {
        "host": host or "localhost",
        "port": port or "5432",
        "user": user or "spe",
        "password": password or "",
        "dbname": dbname or "spe_db",
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
        for c_idx, col in enumerate(common_cols):
            if not are_cells_equal(sq_r[c_idx], pg_r[c_idx], col, table, target_tz):
                table_diffs += 1
                if table_diffs <= 3:
                    print(
                        f"  [DIVERGÊNCIA] {table} (ID {sq_r[0]}), coluna '{col}': SQLite={repr(sq_r[c_idx])} vs PG={repr(pg_r[c_idx])}"
                    )
    return table_diffs


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

    if set(sq_cols) != set(pg_cols):
        missing = sorted(set(sq_cols) - set(pg_cols))
        extra = sorted(set(pg_cols) - set(sq_cols))
        if missing:
            schema_errors.append("ausentes no PostgreSQL: " + ", ".join(missing))
        if extra:
            schema_errors.append("extras no PostgreSQL: " + ", ".join(extra))
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

    sq_count = len(sq_rows)
    pg_count = len(pg_rows)

    if sq_count != pg_count:
        return False, sq_count, pg_count, abs(sq_count - pg_count)

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
        status_msg = "ERRO DE SCHEMA"
        print(f"{table:28} | {'N/A':>7} | {'N/A':>8} | {'N/A':>12} | {status_msg:^12}")
        for error in schema_errors[:5]:
            print(f"  [SCHEMA] {error}")
        return False, 0, 0, max(1, len(schema_errors))

    matched, sq_count, pg_count, diffs = verify_table_data(table, sq_cur, pg_cur, sq_cols, target_tz)
    status_str = "[OK]" if matched else f"[{diffs} ERROS]"
    print(f"{table:28} | {sq_count:>7} | {pg_count:>8} | {diffs:>12} | {status_str:^12}")

    return matched, sq_count, pg_count, diffs


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
        extra = sorted(actual - expected)
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

    all_matched = True
    total_sq_rows = 0
    total_pg_rows = 0
    total_diffs = 0

    try:
        table_errors = validate_table_sets(sq_cur, pg_cur)
        if table_errors:
            for error in table_errors:
                print(f"[SCHEMA] {error}")
            return False

        for table in TABLE_ORDER:
            matched, sq_c, pg_c, diffs = verify_single_table(table, sq_cur, pg_cur, target_tz)
            total_sq_rows += sq_c
            total_pg_rows += pg_c
            total_diffs += diffs
            if not matched:
                all_matched = False

        print("-" * 75)
        print(f"Total de registros: SQLite={total_sq_rows:,} | PostgreSQL={total_pg_rows:,}")
        print(f"Total de divergências detectadas: {total_diffs}")
        final_status = "100% IDÊNTICO E AUDITADO COM SUCESSO" if all_matched else "DIVERGÊNCIAS DETECTADAS"
        print(f"Resultado Final: {final_status}")
        print("=" * 75)
    finally:
        sq_cur.close()
        sq_conn.close()
        pg_cur.close()
        pg_conn.close()

    return all_matched


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
        print(f"Erro na auditoria: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
