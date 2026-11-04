from pathlib import Path

import psycopg2
import pytest
from alembic.config import Config
from sqlalchemy.engine import make_url

from alembic import command


def test_minutes_migration_rounds_and_downgrades(pg_url):
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    url = make_url(pg_url).set(drivername='postgresql').render_as_string(hide_password=False)
    command.downgrade(config, '013')
    with psycopg2.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO users (username) VALUES ('minutos') RETURNING id")
        user_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO adjustment_requests (user_id, adjustment_type, target_date, amount_hours, approved_amount_hours) "
            "VALUES (%s, 'DAILY_EXCESS', '2026-01-01', 1.025, 0.5)", (user_id,),
        )
    command.upgrade(config, 'head')
    with psycopg2.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute('SELECT version_num FROM alembic_version')
        assert cursor.fetchone() == ('013',)
        cursor.execute('SELECT amount_minutes, approved_amount_minutes FROM adjustment_requests')
        assert cursor.fetchone() == (62, 30)
    command.downgrade(config, '013')
    with psycopg2.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute('SELECT amount_hours, approved_amount_hours FROM adjustment_requests')
        assert cursor.fetchone() == pytest.approx((62 / 60, 0.5))
