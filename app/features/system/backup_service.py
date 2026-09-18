import logging
import os
import shutil
import subprocess
import threading
import uuid
import zipfile
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings

logger = logging.getLogger(__name__)

TABLE_ORDER = [
    "alembic_version",
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


PG_ENCODING_UTF8 = "--encoding=UTF8"


class BackupService:
    def __init__(self):
        self._backup_lock = threading.Lock()

    def _get_postgres_connection_params(self) -> dict[str, Any]:
        from sqlalchemy.engine import make_url

        try:
            url = make_url(settings.SQLALCHEMY_DATABASE_URI)
            host = settings.POSTGRES_HOST or url.host or "localhost"
            port = settings.POSTGRES_PORT or url.port or 5432
            user = settings.POSTGRES_USER or url.username or "spe"
            password = settings.POSTGRES_PASSWORD or url.password or ""
            dbname = settings.POSTGRES_DB or url.database or "spe_db"
        except Exception:
            host = settings.POSTGRES_HOST or "localhost"
            port = settings.POSTGRES_PORT or 5432
            user = settings.POSTGRES_USER or "spe"
            password = settings.POSTGRES_PASSWORD or ""
            dbname = settings.POSTGRES_DB or "spe_db"

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "dbname": dbname,
        }

    def _dump_table_data(self, cur: Any, f: Any, table: str) -> None:
        import json

        cur.execute(f'SELECT * FROM "{table}";')
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        if not rows:
            return

        col_identifiers = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict_clause = " ON CONFLICT (version_num) DO NOTHING" if table == "alembic_version" else ""
        insert_tmpl = f'INSERT INTO "{table}" ({col_identifiers}) VALUES ({placeholders}){conflict_clause};\n'

        for row in rows:
            row_formatted = [
                json.dumps(v, ensure_ascii=False)
                if isinstance(v, (dict, list))
                else bytes(v)
                if isinstance(v, memoryview)
                else v
                for v in row
            ]
            mogrified = cur.mogrify(insert_tmpl, row_formatted)
            val_str = mogrified.decode("utf-8") if isinstance(mogrified, bytes) else str(mogrified)
            f.write(val_str)
        f.write("\n")

    def _sync_table_sequences(self, cur: Any, f: Any, sorted_tables: list[str]) -> None:
        for table in sorted_tables:
            if table == "alembic_version":
                continue
            cur.execute("SELECT pg_get_serial_sequence(%s, 'id');", (table,))
            seq_row = cur.fetchone()
            if seq_row and seq_row[0]:
                seq_name = seq_row[0]
                f.write(
                    f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM {table}), 1), "
                    f"EXISTS (SELECT 1 FROM {table}));\n"
                )

    def _dump_postgresql_python(self, output_path: str, params: dict[str, Any]) -> bool:
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=params["host"],
                port=params["port"],
                user=params["user"],
                password=params["password"],
                dbname=params["dbname"],
                connect_timeout=10,
            )
            try:
                with conn.cursor() as cur, open(output_path, "w", encoding="utf-8") as f:
                    cur.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    f.write("BEGIN;\n")
                    f.write("SET client_encoding = 'UTF8';\n")
                    f.write("SET standard_conforming_strings = on;\n\n")
                    f.write("SET CONSTRAINTS ALL DEFERRED;\n\n")

                    cur.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
                    )
                    existing_tables = {r[0] for r in cur.fetchall()}
                    sorted_tables = [t for t in TABLE_ORDER if t in existing_tables]
                    for t in sorted(existing_tables - set(sorted_tables)):
                        sorted_tables.append(t)

                    for table in sorted_tables:
                        self._dump_table_data(cur, f, table)

                    self._sync_table_sequences(cur, f, sorted_tables)

                    f.write("\nCOMMIT;\n")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.exception(f"Erro no dumper PostgreSQL em Python: {type(e).__name__} - {e}", exc_info=False)
            return False

    def _find_pg_dump(self) -> str | None:
        bin_path = shutil.which("pg_dump")
        if bin_path:
            return bin_path
        import glob
        for pattern in [
            r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe",
            r"C:\Program Files (x86)\PostgreSQL\*\bin\pg_dump.exe",
        ]:
            matches = glob.glob(pattern)
            if matches:
                matches.sort(reverse=True)
                return matches[0]
        return None

    def _filter_pg_dump_output(self, raw_bytes: bytes, output_path: str) -> bool:
        from scripts.apply_sql_to_postgresql import strip_sql_comments

        text = raw_bytes.decode("utf-8")
        text = "".join(
            line for line in text.splitlines(keepends=True)
            if not line.lstrip().startswith((r"\restrict", r"\unrestrict"))
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(strip_sql_comments(text))
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    def _dump_postgresql_schema_python(self, output_path: str) -> bool:
        try:
            from scripts.db_manager import get_ddl_sql
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(get_ddl_sql(include_alembic_version=True))
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            logger.exception(f"Erro ao gerar schema via Python: {type(e).__name__} - {e}", exc_info=False)
            return False

    def _dump_postgresql_schema(self, output_path: str) -> bool:
        params = self._get_postgres_connection_params()
        pg_dump_bin = self._find_pg_dump()

        if pg_dump_bin:
            try:
                env = os.environ.copy()
                if params["password"]:
                    env["PGPASSWORD"] = str(params["password"])
                cmd = [
                    pg_dump_bin,
                    "-h", str(params["host"]),
                    "-p", str(params["port"]),
                    "-U", str(params["user"]),
                    "-d", str(params["dbname"]),
                    "--schema-only",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-privileges",
                    PG_ENCODING_UTF8,
                ]
                proc = subprocess.run(cmd, env=env, check=True, capture_output=True)
                if proc.stdout and self._filter_pg_dump_output(proc.stdout, output_path):
                    return True
            except Exception as e:
                logger.warning(f"Host pg_dump schema falhou: {e}. Tentando fallback...")

        if shutil.which("docker"):
            try:
                cmd = [
                    "docker", "exec",
                    "-e", f"PGPASSWORD={params['password']}",
                    "spe_postgres",
                    "pg_dump",
                    "-U", str(params["user"]),
                    "-d", str(params["dbname"]),
                    "--schema-only",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-privileges",
                    PG_ENCODING_UTF8,
                ]
                proc = subprocess.run(cmd, check=True, capture_output=True)
                if proc.stdout and self._filter_pg_dump_output(proc.stdout, output_path):
                    return True
            except Exception as e:
                logger.warning(f"Docker pg_dump schema falhou: {e}. Tentando fallback...")

        return self._dump_postgresql_schema_python(output_path)

    def _dump_postgresql_inserts(self, output_path: str) -> bool:
        params = self._get_postgres_connection_params()
        pg_dump_bin = self._find_pg_dump()

        if pg_dump_bin:
            try:
                env = os.environ.copy()
                if params["password"]:
                    env["PGPASSWORD"] = str(params["password"])
                cmd = [
                    pg_dump_bin,
                    "-h", str(params["host"]),
                    "-p", str(params["port"]),
                    "-U", str(params["user"]),
                    "-d", str(params["dbname"]),
                    "--data-only",
                    "--inserts",
                    "--column-inserts",
                    "--no-owner",
                    "--no-privileges",
                    PG_ENCODING_UTF8,
                ]
                proc = subprocess.run(cmd, env=env, check=True, capture_output=True)
                if proc.stdout and self._filter_pg_dump_output(proc.stdout, output_path):
                    return True
            except Exception as e:
                logger.warning(f"Host pg_dump inserts falhou: {e}. Tentando fallback...")

        if shutil.which("docker"):
            try:
                cmd = [
                    "docker", "exec",
                    "-e", f"PGPASSWORD={params['password']}",
                    "spe_postgres",
                    "pg_dump",
                    "-U", str(params["user"]),
                    "-d", str(params["dbname"]),
                    "--data-only",
                    "--inserts",
                    "--column-inserts",
                    "--no-owner",
                    "--no-privileges",
                    PG_ENCODING_UTF8,
                ]
                proc = subprocess.run(cmd, check=True, capture_output=True)
                if proc.stdout and self._filter_pg_dump_output(proc.stdout, output_path):
                    return True
            except Exception as e:
                logger.warning(f"Docker pg_dump inserts falhou: {e}. Tentando fallback...")

        return self._dump_postgresql_python(output_path, params)

    def create_safe_backup(self) -> str | None:
        with self._backup_lock:
            tz = ZoneInfo(settings.TIMEZONE)
            timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            backup_filename = f"temp_backup_{timestamp}_{unique_id}.sql"

            try:
                success = self._dump_postgresql_schema(backup_filename)
                if success and os.path.exists(backup_filename) and os.path.getsize(backup_filename) > 0:
                    return backup_filename

                if os.path.exists(backup_filename):
                    try:
                        os.remove(backup_filename)
                    except OSError:
                        pass
                logger.error("Falha ao gerar schema do PostgreSQL.")
                return None
            except Exception as e:
                logger.exception(
                    f"Erro de banco PostgreSQL ao criar backup seguro: {type(e).__name__} - {e}",
                    exc_info=False
                )
                if os.path.exists(backup_filename):
                    try:
                        os.remove(backup_filename)
                    except OSError:
                        pass
                return None

    def create_sql_dump(self) -> str | None:
        tz = ZoneInfo(settings.TIMEZONE)
        timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        sql_filename = f"temp_inserts_{timestamp}_{unique_id}.sql"

        try:
            success = self._dump_postgresql_inserts(sql_filename)
            if success and os.path.exists(sql_filename) and os.path.getsize(sql_filename) > 0:
                return sql_filename

            if os.path.exists(sql_filename):
                try:
                    os.remove(sql_filename)
                except OSError:
                    pass
            logger.error("Falha ao gerar dump de inserts do PostgreSQL.")
            return None
        except Exception as e:
            logger.exception(
                f"Erro ao gerar dump SQL de inserts: {type(e).__name__} - {e}",
                exc_info=False
            )
            if os.path.exists(sql_filename):
                try:
                    os.remove(sql_filename)
                except OSError:
                    pass
            return None

    def compress_files(self, files_to_compress: dict[str, str], output_zip_path: str) -> str | None:
        try:
            with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path, arcname in files_to_compress.items():
                    if file_path and os.path.exists(file_path):
                        zipf.write(file_path, arcname=arcname)
            return output_zip_path
        except Exception as e:
            logger.exception(
                f"Erro ao compactar arquivos para {output_zip_path}: {type(e).__name__} - {e}",
                exc_info=False
            )
            return None


backup_service = BackupService()
