import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.apply_sql_to_postgresql import (
    apply_sql_file,
    get_pg_credentials,
    load_environment,
    restore_backup,
)
from scripts.export_sqlite_to_postgresql import export_sqlite_to_postgresql
from scripts.verify_parity import verify_parity
FILENAME_SPE_DUMP = "spe_dump.sql"
FILENAME_SPE_DB = "spe-db.sql"
FILENAME_SPE_ZIP = "spe.zip"
DEFAULT_SQLITE_PATH = ROOT_DIR / "spe.db"
DEFAULT_SCHEMA_PATH = ROOT_DIR / FILENAME_SPE_DB
DEFAULT_DUMP_PATH = ROOT_DIR / FILENAME_SPE_DUMP
DEFAULT_ZIP_PATH = ROOT_DIR / FILENAME_SPE_ZIP
DEFAULT_DML_PATH = ROOT_DIR / "scripts" / "data_inserts_postgresql.sql"


def _extract_extensions_and_types(creds: dict[str, str]) -> list[str]:
    import psycopg2

    parts: list[str] = []
    try:
        conn = psycopg2.connect(
            host=creds["host"],
            port=int(creds["port"]),
            user=creds["user"],
            password=creds["password"],
            dbname=creds["dbname"],
            connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname != 'plpgsql';")
            for ext in cur.fetchall():
                parts.append(f'CREATE EXTENSION IF NOT EXISTS "{ext[0]}";')
            parts.append("")

            cur.execute("""
                SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                JOIN pg_namespace n ON t.typnamespace = n.oid
                WHERE n.nspname = 'public'
                GROUP BY t.typname;
            """)
            for typ, labels in cur.fetchall():
                labels_str = ", ".join(f"'{lbl}'" for lbl in labels)
                parts.append(
                    f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{typ}') "
                    f"THEN CREATE TYPE {typ} AS ENUM ({labels_str}); END IF; END $$;"
                )
            parts.append("")
        conn.close()
    except Exception:
        pass
    return parts


def _extract_tables_and_indexes(engine: Any, metadata: Any, include_alembic_version: bool) -> list[str]:
    from sqlalchemy.schema import CreateIndex, CreateTable

    parts: list[str] = []
    for table_name, table in metadata.tables.items():
        if table_name == "alembic_version" and not include_alembic_version:
            continue
        create_table_stmt = str(CreateTable(table).compile(engine)).strip()
        parts.append(f"{create_table_stmt};")
        for idx in table.indexes:
            create_index_stmt = str(CreateIndex(idx).compile(engine)).strip()
            parts.append(f"{create_index_stmt};")
        parts.append("")
    return parts


def extract_live_ddl_from_postgres(include_alembic_version: bool = False) -> str:
    from sqlalchemy import create_engine, MetaData

    creds = get_pg_credentials()
    url = f"postgresql://{creds['user']}:{creds['password']}@{creds['host']}:{creds['port']}/{creds['dbname']}"
    engine = create_engine(url)
    metadata = MetaData()
    metadata.reflect(bind=engine)

    ddl_parts = [
        "SET client_encoding = 'UTF8';",
        "SET standard_conforming_strings = on;",
        "SET check_function_bodies = false;",
        "SET client_min_messages = warning;",
        "SET row_security = off;\n",
    ]
    ddl_parts.extend(_extract_extensions_and_types(creds))
    ddl_parts.extend(_extract_tables_and_indexes(engine, metadata, include_alembic_version))

    return "\n".join(ddl_parts)


def _load_fallback_migration_ddl(include_alembic_version: bool) -> str:
    migration_file = ROOT_DIR / "alembic" / "versions" / "001_db_base.py"
    if not migration_file.exists():
        raise FileNotFoundError(f"Arquivo de migração base não encontrado: {migration_file}")

    content = migration_file.read_text(encoding="utf-8")
    match = re.search(r'SCHEMA_SQL\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if not match:
        raise ValueError("Constante SCHEMA_SQL não encontrada na migração 001_db_base.py")

    schema_sql = match.group(1).strip()
    alembic_stmt = (
        "\nCREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);\n"
        "INSERT INTO alembic_version (version_num) VALUES ('001') ON CONFLICT (version_num) DO NOTHING;\n"
    )
    return f"{schema_sql}\n{alembic_stmt}" if include_alembic_version else schema_sql


def get_ddl_sql(
    include_alembic_version: bool = True,
    include_transaction_control: bool = True,
) -> str:
    try:
        full_sql = extract_live_ddl_from_postgres(include_alembic_version=include_alembic_version)
    except Exception:
        full_sql = _load_fallback_migration_ddl(include_alembic_version=include_alembic_version)

    if include_transaction_control:
        return f"BEGIN;\n{full_sql.strip()}\nCOMMIT;\n"
    return f"{full_sql.strip()}\n"


def find_pg_binary(name: str) -> str | None:
    bin_path = shutil.which(name)
    if bin_path:
        return bin_path
    import glob

    for pattern in [
        rf"C:\Program Files\PostgreSQL\*\bin\{name}.exe",
        rf"C:\Program Files (x86)\PostgreSQL\*\bin\{name}.exe",
    ]:
        matches = glob.glob(pattern)
        if matches:
            matches.sort(reverse=True)
            return matches[0]
    return None


def _run_local_pg_dump(output_path: Path, creds: dict[str, str], pg_dump: str, extra_flags: list[str]) -> bool:
    env = os.environ.copy()
    if creds.get("password"):
        env["PGPASSWORD"] = str(creds["password"])
    cmd = [
        pg_dump,
        "-h", str(creds.get("host", "localhost")),
        "-p", str(creds.get("port", 5432)),
        "-U", str(creds.get("user", "spe")),
        "-d", str(creds.get("dbname", "spe_db")),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--encoding=UTF8",
        *extra_flags,
        "-f", str(output_path),
    ]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def _run_docker_pg_dump(output_path: Path, creds: dict[str, str], extra_flags: list[str]) -> bool:
    if not shutil.which("docker"):
        return False
    cmd = [
        "docker", "exec",
        "-e", f"PGPASSWORD={creds.get('password', '')}",
        "spe_postgres",
        "pg_dump",
        "-U", str(creds.get("user", "spe")),
        "-d", str(creds.get("dbname", "spe_db")),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--encoding=UTF8",
        *extra_flags,
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode == 0 and res.stdout:
        with open(output_path, "wb") as f:
            f.write(res.stdout)
        return True
    return False


def dump_schema_ddl(output_path: Path = DEFAULT_SCHEMA_PATH) -> None:
    creds = get_pg_credentials()
    pg_dump = find_pg_binary("pg_dump")
    flags = ["--schema-only"]

    print(f"Extraindo DDL do banco PostgreSQL para: {output_path.name}...")
    if pg_dump and _run_local_pg_dump(output_path, creds, pg_dump, flags):
        print(f"[OK] DDL extraída com sucesso via pg_dump! ({output_path.stat().st_size:,} bytes)")
        return

    if _run_docker_pg_dump(output_path, creds, flags):
        print(f"[OK] DDL extraída com sucesso via Docker! ({output_path.stat().st_size:,} bytes)")
        return

    ddl = extract_live_ddl_from_postgres(include_alembic_version=False)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ddl)
    print(f"[OK] DDL extraída com sucesso via introspecção live! ({output_path.stat().st_size:,} bytes)")


def dump_data_inserts(output_path: Path = DEFAULT_DUMP_PATH) -> None:
    creds = get_pg_credentials()
    pg_dump = find_pg_binary("pg_dump")
    flags = ["--data-only", "--inserts", "--column-inserts"]

    print(f"Extraindo inserts de dados do PostgreSQL para: {output_path.name}...")
    if pg_dump and _run_local_pg_dump(output_path, creds, pg_dump, flags):
        print(f"[OK] Inserts extraídos com sucesso via pg_dump! ({output_path.stat().st_size:,} bytes)")
        return

    if _run_docker_pg_dump(output_path, creds, flags):
        print(f"[OK] Inserts extraídos com sucesso via Docker! ({output_path.stat().st_size:,} bytes)")
        return

    from app.features.system.backup_service import backup_service
    params = backup_service._get_postgres_connection_params()
    if backup_service._dump_postgresql_python(str(output_path), params):
        print(f"[OK] Inserts extraídos com sucesso via dumper Python! ({output_path.stat().st_size:,} bytes)")
        return

    raise RuntimeError("Não foi possível extrair inserts do PostgreSQL.")


def dump_database(
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    dump_path: Path = DEFAULT_DUMP_PATH,
    zip_path: Path = DEFAULT_ZIP_PATH,
) -> None:
    print("Iniciando dump completo desmembrado do PostgreSQL...")
    dump_schema_ddl(schema_path)
    dump_data_inserts(dump_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(schema_path, arcname=FILENAME_SPE_DB)
        z.write(dump_path, arcname=FILENAME_SPE_DUMP)
    print(f"[OK] Pacote de backup completo gerado em {zip_path.name} ({zip_path.stat().st_size:,} bytes)")


def restore_database(input_path: Path = DEFAULT_ZIP_PATH) -> None:
    restore_backup(input_path)
    print("Banco de dados PostgreSQL restaurado com sucesso.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilitário de migração, geração de SQL e gerenciamento do banco de dados."
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="Gera dump completo desmembrado: DDL (spe-db.sql), inserts (spe_dump.sql) e pacote ZIP",
    )
    parser.add_argument(
        "--dump-ddl",
        action="store_true",
        help="Extrai apenas a DDL da estrutura atual do PostgreSQL",
    )
    parser.add_argument(
        "--dump-data",
        action="store_true",
        help="Extrai apenas os inserts de dados do PostgreSQL",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restaura o PostgreSQL a partir de um arquivo de backup ou dump",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_ZIP_PATH,
        help="Caminho do arquivo de backup para restauração",
    )
    parser.add_argument(
        "--export-sqlite",
        action="store_true",
        help="Extrai os dados do SQLite e gera data_inserts_postgresql.sql",
    )
    parser.add_argument(
        "--apply-dump",
        action="store_true",
        help="Aplica data_inserts_postgresql.sql no PostgreSQL de forma atômica",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verifica paridade célula a célula entre SQLite e PostgreSQL",
    )
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="Caminho do arquivo SQLite (padrão: spe.db)",
    )
    parser.add_argument(
        "--dml-out",
        type=Path,
        default=DEFAULT_DML_PATH,
        help="Caminho de saída do script de dados SQL",
    )

    args = parser.parse_args()

    if not any([args.dump, args.dump_ddl, args.dump_data, args.restore, args.export_sqlite, args.apply_dump, args.verify]):
        parser.print_help()
        sys.exit(0)

    try:
        if args.dump:
            dump_database()
        if args.dump_ddl:
            dump_schema_ddl()
        if args.dump_data:
            dump_data_inserts()
        if args.restore:
            restore_database(args.file)
        if args.export_sqlite:
            export_sqlite_to_postgresql(args.sqlite_db, args.dml_out)
        if args.apply_dump:
            apply_sql_file(args.dml_out, truncate_first=True)
        if args.verify and not verify_parity(args.sqlite_db):
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERRO]: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
