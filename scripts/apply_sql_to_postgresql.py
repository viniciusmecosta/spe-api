import argparse
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DML_PATH = ROOT_DIR / "scripts" / "data_inserts_postgresql.sql"
FILENAME_SPE_DUMP = "spe_dump.sql"
FILENAME_SPE_DB = "spe-db.sql"
CURRENT_SCHEMA_REVISION = "001"

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
                raise RuntimeError(f"Não foi possível conectar ao PostgreSQL após {max_retries} tentativas: {e}") from e
            time.sleep(delay)


def truncate_database_tables(cursor: Any) -> None:
    truncate_query = f"TRUNCATE TABLE {', '.join(TABLE_ORDER)} RESTART IDENTITY CASCADE;"
    cursor.execute(truncate_query)
    cursor.execute("DELETE FROM alembic_version;")


def apply_sql_file(sql_path: Path, truncate_first: bool = True) -> None:
    if not sql_path.exists():
        raise FileNotFoundError(f"Arquivo SQL não encontrado: {sql_path}")

    creds = get_pg_credentials()
    conn = connect_with_retry(creds)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        if truncate_first:
            truncate_database_tables(cursor)

        sql_content = sql_path.read_text(encoding="utf-8")
        cursor.execute("SET CONSTRAINTS ALL DEFERRED;")
        cursor.execute(sql_content)
        cursor.execute(
            "INSERT INTO alembic_version (version_num) VALUES (%s) ON CONFLICT (version_num) DO NOTHING;",
            (CURRENT_SCHEMA_REVISION,),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Falha ao aplicar SQL no PostgreSQL: {e}") from e
    finally:
        cursor.close()
        conn.close()


def find_data_file_in_dir(tmp_dir: Path) -> Path | None:
    for name in [FILENAME_SPE_DUMP, "data.sql", "data_inserts_postgresql.sql"]:
        f = tmp_dir / name
        if f.exists():
            return f
    for p in tmp_dir.glob("*.sql"):
        if p.name != FILENAME_SPE_DB:
            return p
    return None


def find_backup_source() -> Path | None:
    candidates = [
        ROOT_DIR / "spe.zip",
        ROOT_DIR / "scripts" / "spe.zip",
        ROOT_DIR / FILENAME_SPE_DUMP,
        ROOT_DIR / "scripts" / FILENAME_SPE_DUMP,
        DEFAULT_DML_PATH,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def restore_backup(source_path: Path | None = None) -> None:
    target = source_path or find_backup_source()
    if not target or not target.exists():
        raise FileNotFoundError("Arquivo de backup ou dump não encontrado.")

    if target.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(target, "r") as z:
                z.extractall(tmp_dir)
            data_file = find_data_file_in_dir(Path(tmp_dir))
            if not data_file:
                raise FileNotFoundError("Nenhum arquivo de dados SQL encontrado no ZIP.")
            apply_sql_file(data_file, truncate_first=True)
            return

    apply_sql_file(target, truncate_first=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica dump SQL ou restaura backup no PostgreSQL de forma atômica."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_DML_PATH,
        help="Caminho do arquivo SQL ou ZIP de backup",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Modo de restauração: busca backup zip/dump de email, limpa registros e aplica",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Não limpa os dados existentes antes da aplicação",
    )

    args = parser.parse_args()

    try:
        if args.restore:
            restore_backup(args.file if args.file != DEFAULT_DML_PATH else None)
            print("Backup restaurado e dados aplicados com sucesso no PostgreSQL.")
        else:
            apply_sql_file(args.file, truncate_first=not args.no_truncate)
            print(f"Dump SQL '{args.file.name}' aplicado com sucesso no PostgreSQL.")
    except Exception as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
