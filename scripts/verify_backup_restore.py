import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

try:
    from scripts.apply_sql_to_postgresql import (
        ROOT_DIR, find_backup_source, get_pg_credentials, load_environment, restore_backup,
    )
except ModuleNotFoundError:
    from apply_sql_to_postgresql import (
        ROOT_DIR, find_backup_source, get_pg_credentials, load_environment, restore_backup,
    )


def verify_restore(source: Path | None = None) -> dict:
    load_environment()
    source = source or find_backup_source()
    if source is None or not source.is_file():
        raise FileNotFoundError("Backup não encontrado")
    credentials = get_pg_credentials()
    database = "spe_restore_test_" + uuid.uuid4().hex[:16]
    admin = psycopg2.connect(
        host=credentials["host"], port=int(credentials["port"]),
        user=credentials["user"], password=credentials["password"], dbname="postgres",
    )
    admin.autocommit = True
    created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database))
            )
            created = True

        environment = os.environ.copy()
        environment["POSTGRES_DB"] = database
        original_uri = environment.get("SQLALCHEMY_DATABASE_URI", "")
        if not original_uri:
            raise ValueError("SQLALCHEMY_DATABASE_URI não configurada")
        environment["SQLALCHEMY_DATABASE_URI"] = make_url(original_uri).set(database=database).render_as_string(
            hide_password=False
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT_DIR, env=environment, check=True,
        )
        old_db = os.environ.get("POSTGRES_DB")
        old_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
        try:
            os.environ["POSTGRES_DB"] = database
            os.environ["SQLALCHEMY_DATABASE_URI"] = environment["SQLALCHEMY_DATABASE_URI"]
            return restore_backup(source, allow_destructive=True, expected_database=database)
        finally:
            if old_db is None:
                os.environ.pop("POSTGRES_DB", None)
            else:
                os.environ["POSTGRES_DB"] = old_db
            if old_uri is None:
                os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
            else:
                os.environ["SQLALCHEMY_DATABASE_URI"] = old_uri
    finally:
        if created:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database,),
                )
                cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
        admin.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Testa o restore em um banco PostgreSQL descartável")
    parser.add_argument("--file", type=Path, help="Backup a testar; por padrão busca em scripts/ ou na raiz")
    args = parser.parse_args()
    result = verify_restore(args.file)
    print(f"Restore validado em banco descartável: {result['statements']} comandos aplicados")


if __name__ == "__main__":
    main()
