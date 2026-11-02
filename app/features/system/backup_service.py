import logging
import os
import shutil
import subprocess
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.database.connection import postgres_connection_params
from app.features.system.backup_crypto import encrypt_backup
from app.features.system.backup_manifest import add_manifest
from app.shared.sql_text import remove_psql_directives, sql_lines

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
        self._backup_lock = threading.RLock()
        self._snapshot_id: str | None = None
        self._snapshot_counts: dict[str, int] | None = None

    @staticmethod
    def _open_private(path: str, mode: str):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, mode, encoding="utf-8" if "b" not in mode else None)

    @contextmanager
    def consistent_snapshot(self):
        import psycopg2
        from psycopg2 import sql

        with self._backup_lock:
            params = self._get_postgres_connection_params()
            connection = psycopg2.connect(**params)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    cursor.execute("SELECT pg_export_snapshot()")
                    self._snapshot_id = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                        "AND table_name != 'alembic_version'"
                    )
                    tables = [row[0] for row in cursor.fetchall()]
                    self._snapshot_counts = {}
                    for table in tables:
                        cursor.execute(
                            sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(table))
                        )
                        self._snapshot_counts[table] = cursor.fetchone()[0]
                yield
            finally:
                self._snapshot_id = None
                self._snapshot_counts = None
                connection.rollback()
                connection.close()

    def _dump_with_snapshot(self, output_path: str, *, schema_only: bool) -> bool:
        snapshot = self._snapshot_id
        if not snapshot:
            return False
        params = self._get_postgres_connection_params()
        flags = ["--schema-only", "--clean", "--if-exists"] if schema_only else [
            "--data-only", "--inserts", "--column-inserts"
        ]
        common = [
            "-U", str(params["user"]), "-d", str(params["dbname"]),
            "--no-owner", "--no-privileges", PG_ENCODING_UTF8,
            f"--snapshot={snapshot}", *flags,
        ]
        commands = self._snapshot_commands(params, common, self._find_pg_dump())
        for command, environment in commands:
            if self._run_snapshot_dump(command, environment, output_path):
                return True
        Path(output_path).unlink(missing_ok=True)
        return False

    def _snapshot_commands(self, params, common, host_bin):
        if not host_bin:
            return []
        return [(
            [host_bin, "-h", str(params["host"]), "-p", str(params["port"]), *common],
            {**os.environ, "PGPASSWORD": str(params["password"])},
        )]

    def _run_snapshot_dump(self, command, environment, output_path: str) -> bool:
        with self._open_private(output_path, "wb") as output:
            result = subprocess.run(command, env=environment, stdout=output, stderr=subprocess.PIPE, check=False)
        if result.returncode == 0 and os.path.getsize(output_path) > 0:
            self._remove_pg_dump_directives(output_path)
            return True
        logger.warning(
            "pg_dump com snapshot falhou: %s",
            result.stderr.decode("utf-8", "replace")[:500],
        )
        return False

    @staticmethod
    def _remove_pg_dump_directives(output_path: str) -> None:
        remove_psql_directives(Path(output_path))

    def _get_postgres_connection_params(self) -> dict[str, Any]:
        return postgres_connection_params(settings.SQLALCHEMY_DATABASE_URI, settings.model_dump())

    def _dump_table_data(self, cur: Any, f: Any, table: str) -> None:
        import json

        cur.execute(f'SELECT * FROM "{table}";')
        rows = cur.fetchmany(1000)
        if not rows:
            return
        columns = [desc[0] for desc in cur.description]

        col_identifiers = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict_clause = " ON CONFLICT (version_num) DO NOTHING" if table == "alembic_version" else ""
        insert_tmpl = f'INSERT INTO "{table}" ({col_identifiers}) VALUES ({placeholders}){conflict_clause};\n'

        while rows:
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
            rows = cur.fetchmany(1000)
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
                with conn.cursor() as cur, self._open_private(output_path, "w") as f:
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
                    sorted_tables.extend(sorted(existing_tables - set(sorted_tables)))

                    for table in sorted_tables:
                        with conn.cursor(name=f"spe_backup_{uuid.uuid4().hex}") as data_cursor:
                            self._dump_table_data(data_cursor, f, table)

                    self._sync_table_sequences(cur, f, sorted_tables)

                    f.write("\nCOMMIT;\n")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.exception(f'Erro no dumper PostgreSQL em Python: {type(e).__name__}')
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
        text = raw_bytes.decode("utf-8")
        text = "".join(sql_lines(text.splitlines(keepends=True)))
        with self._open_private(output_path, "w") as f:
            f.write(text)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    @staticmethod
    def _remove_file_safely(path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            os.remove(path)
        except OSError:
            pass

    def _load_live_row_counts(self) -> dict[str, int]:
        import psycopg2
        from psycopg2 import sql

        params = self._get_postgres_connection_params()
        with psycopg2.connect(**params) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' AND table_name != 'alembic_version'")
            tables = [row[0] for row in cursor.fetchall()]
            counts = {}
            for table in tables:
                cursor.execute(sql.SQL('SELECT COUNT(*) FROM public.{}').format(sql.Identifier(table)))
                counts[table] = cursor.fetchone()[0]
            return counts

    def _dump_postgresql_schema(self, output_path: str) -> bool:
        if self._snapshot_id:
            return self._dump_with_snapshot(output_path, schema_only=True)
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
            except Exception:
                logger.exception("pg_dump schema falhou")

        return False

    def _dump_postgresql_inserts(self, output_path: str) -> bool:
        if self._snapshot_id:
            return self._dump_with_snapshot(output_path, schema_only=False)
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
            except Exception:
                logger.exception("pg_dump inserts falhou; tentando exportador Python no mesmo banco")

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

                self._remove_file_safely(backup_filename)
                logger.error("Falha ao gerar schema do PostgreSQL.")
                return None
            except Exception as e:
                logger.exception(
                    f'Erro de banco PostgreSQL ao criar backup seguro: {type(e).__name__}')
                self._remove_file_safely(backup_filename)
                return None

    def create_sql_dump(self) -> str | None:
        tz = ZoneInfo(settings.TIMEZONE)
        timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        sql_filename = f"temp_inserts_{timestamp}_{unique_id}.sql"

        try:
            success = self._dump_postgresql_inserts(sql_filename)
            if success and os.path.exists(sql_filename) and os.path.getsize(sql_filename) > 0:
                row_counts = (
                    self._snapshot_counts
                    if self._snapshot_counts is not None
                    else self._load_live_row_counts()
                )
                add_manifest(Path(sql_filename), row_counts)
                return sql_filename

            self._remove_file_safely(sql_filename)
            logger.error("Falha ao gerar dump de inserts do PostgreSQL.")
            return None
        except Exception as e:
            logger.exception(f'Erro ao gerar dump SQL de inserts: {type(e).__name__}')
            self._remove_file_safely(sql_filename)
            return None

    def compress_files(self, files_to_compress: dict[str, str], output_zip_path: str) -> str | None:
        try:
            with self._open_private(output_zip_path, 'wb') as output, zipfile.ZipFile(output, 'w',
                                                                                      zipfile.ZIP_DEFLATED) as zipf:
                for file_path, arcname in files_to_compress.items():
                    if file_path and os.path.exists(file_path):
                        zipf.write(file_path, arcname=arcname)
            return str(encrypt_backup(Path(output_zip_path), settings.SECRET_KEY))
        except Exception as e:
            logger.exception(
                f'Erro ao compactar arquivos para {output_zip_path}: {type(e).__name__}')
            return None
        finally:
            Path(output_zip_path).unlink(missing_ok=True)


backup_service = BackupService()
