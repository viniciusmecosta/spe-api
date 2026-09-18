import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime
from datetime import time as dtime
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

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = ROOT_DIR / "spe.db"

TABLE_ORDER = [
    "companies",
    "printers",
    "users",
    "device_credentials",
    "firmwares",
    "holidays",
    "user_biometrics",
    "user_work_schedule_configs",
    "time_records",
    "adjustment_requests",
    "adjustment_attachments",
    "payroll_closures",
    "audit_logs",
    "routine_logs",
]

BOOLEAN_COLUMNS = {
    "companies": {"auto_print_receipt"},
    "printers": {"status"},
    "users": {
        "is_active",
        "can_manual_punch_desktop",
        "can_manual_punch_mobile",
        "can_export_report",
        "is_exempt_from_rules",
        "is_tolerance_exempt",
        "auto_print_receipt",
    },
    "device_credentials": {"is_active"},
    "user_work_schedule_configs": {"is_daily_excess_enabled"},
    "time_records": {"is_ignored", "is_verified"},
    "payroll_closures": {"is_closed"},
}

JSONB_COLUMNS = {
    "audit_logs": {"old_data", "new_data"},
}


def load_environment() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists() and load_dotenv:
        load_dotenv(dotenv_path=env_path, override=True)


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
    if isinstance(pg_val, float) or isinstance(sq_val, float):
        try:
            return abs(float(sq_val) - float(pg_val)) < 1e-5
        except (ValueError, TypeError):
            return None
    if isinstance(pg_val, int) and isinstance(sq_val, int):
        return sq_val == pg_val
    return None


def are_cells_equal(sq_val: Any, pg_val: Any, col_name: str, table_name: str, tz: ZoneInfo) -> bool:
    if table_name in JSONB_COLUMNS and col_name in JSONB_COLUMNS[table_name]:
        return parse_jsonb_value(sq_val) == parse_jsonb_value(pg_val)

    if sq_val is None and pg_val is None:
        return True
    if sq_val is None or pg_val is None:
        return False

    if table_name in BOOLEAN_COLUMNS and col_name in BOOLEAN_COLUMNS[table_name]:
        return bool(sq_val) == bool(pg_val)

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


def get_table_columns(table: str, sq_cur: Any, pg_cur: Any, pg_conn: Any) -> tuple[list[str], list[str]]:
    sq_cur.execute(f"PRAGMA table_info({table})")
    sq_cols = [c[1] for c in sq_cur.fetchall()]

    try:
        pg_cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        pg_cols = [c[0] for c in pg_cur.fetchall()]
    except Exception:
        pg_conn.rollback()
        pg_cols = []

    return sq_cols, pg_cols


def verify_table_data(
    table: str,
    sq_cur: Any,
    pg_cur: Any,
    common_cols: list[str],
    target_tz: ZoneInfo,
) -> tuple[bool, int, int, int]:
    cols_sql = ", ".join(f'"{c}"' for c in common_cols)
    sq_cur.execute(f'SELECT {cols_sql} FROM "{table}" ORDER BY "id"')
    pg_cur.execute(f'SELECT {cols_sql} FROM "{table}" ORDER BY "id"')

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
    pg_conn: Any,
    target_tz: ZoneInfo,
) -> tuple[bool, int, int, int]:
    sq_cols, pg_cols = get_table_columns(table, sq_cur, pg_cur, pg_conn)

    if not sq_cols or not pg_cols or set(sq_cols) != set(pg_cols):
        status_msg = "ERRO DE SCHEMA"
        print(f"{table:28} | {'N/A':>7} | {'N/A':>8} | {'N/A':>12} | {status_msg:^12}")
        return False, 0, 0, 1

    matched, sq_count, pg_count, diffs = verify_table_data(table, sq_cur, pg_cur, sq_cols, target_tz)
    status_str = "[OK]" if matched else f"[{diffs} ERROS]"
    print(f"{table:28} | {sq_count:>7} | {pg_count:>8} | {diffs:>12} | {status_str:^12}")

    return matched, sq_count, pg_count, diffs


def verify_parity(sqlite_path: Path = DEFAULT_SQLITE_PATH) -> bool:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Arquivo SQLite não encontrado: {sqlite_path}")

    creds = get_pg_credentials()
    tz_name = get_timezone()
    target_tz = ZoneInfo(tz_name)

    sq_conn = sqlite3.connect(sqlite_path)
    sq_cur = sq_conn.cursor()

    pg_conn = connect_with_retry(creds)
    pg_cur = pg_conn.cursor()

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
        for table in TABLE_ORDER:
            matched, sq_c, pg_c, diffs = verify_single_table(table, sq_cur, pg_cur, pg_conn, target_tz)
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
