from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_schedule_minutes_migration_converts_and_restores_values(pg_url):
    engine = create_engine(make_url(pg_url).set(drivername="postgresql"))
    migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("011").module
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA migration_minutes_test"))
        connection.execute(text("SET LOCAL search_path TO migration_minutes_test"))
        connection.execute(text(
            "CREATE TABLE user_work_schedule_configs (id INTEGER PRIMARY KEY, daily_hours DOUBLE PRECISION NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO user_work_schedule_configs VALUES "
            "(1, 8.0), (2, 1.5), (3, 1.25), (4, 1.0), (5, 0.5)"
        ))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(text(
                "SELECT id, daily_minutes FROM user_work_schedule_configs ORDER BY id"
            )).all() == [(1, 480), (2, 90), (3, 75), (4, 60), (5, 30)]
            migration.downgrade()
            assert connection.execute(text(
                "SELECT id, daily_hours FROM user_work_schedule_configs ORDER BY id"
            )).all() == [(1, 8.0), (2, 1.5), (3, 1.25), (4, 1.0), (5, 0.5)]
        connection.execute(text("DROP SCHEMA migration_minutes_test CASCADE"))
    engine.dispose()
