from pathlib import Path

import psycopg2
from alembic.config import Config
from sqlalchemy.engine import make_url

from alembic import command


def test_period_index_migration_upgrade_and_downgrade(pg_url):
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    url = make_url(pg_url).set(drivername='postgresql').render_as_string(hide_password=False)

    def index_exists():
        with psycopg2.connect(url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.idx_tr_date_id') IS NOT NULL")
            return cursor.fetchone()[0]

    assert index_exists()
    command.downgrade(config, '011')
    assert not index_exists()
    command.upgrade(config, 'head')
    assert index_exists()
