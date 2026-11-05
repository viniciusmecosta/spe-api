import os
import subprocess
from pathlib import Path

import psycopg2
from sqlalchemy.engine import make_url


def test_make_reset_recreates_database_only_at_initial_revision(pg_url):
    root = Path(__file__).resolve().parents[2]
    url = make_url(pg_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg2.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TABLE reset_marker (id INTEGER PRIMARY KEY)")

    env = os.environ.copy()
    env["SQLALCHEMY_DATABASE_URI"] = pg_url
    for _ in range(2):
        result = subprocess.run(
            ["make", "db-reset-001"], cwd=root, env=env, capture_output=True, text=True, check=False, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        with psycopg2.connect(url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            assert cursor.fetchone() == ("001",)
            cursor.execute("SELECT to_regclass('public.reset_marker')")
            assert cursor.fetchone() == (None,)
            cursor.execute("SELECT to_regclass('public.users')")
            assert cursor.fetchone()[0] == "users"
