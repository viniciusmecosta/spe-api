import psycopg2
from alembic.config import Config
from psycopg2 import sql
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings


def reset_database() -> None:
    url = make_url(settings.SQLALCHEMY_DATABASE_URI)
    database = url.database
    if url.get_backend_name() != "postgresql" or not database or database in {"postgres", "template0", "template1"}:
        raise ValueError("Informe um banco de aplicação válido para recriar.")

    admin_url = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    connection = psycopg2.connect(admin_url)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (database,))
            owner = cursor.fetchone()
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))
            statement = sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(database))
            if owner:
                statement += sql.SQL("OWNER {} ").format(sql.Identifier(owner[0]))
            cursor.execute(statement)
    finally:
        connection.close()

    command.upgrade(Config("alembic.ini"), "001")


if __name__ == "__main__":
    reset_database()
