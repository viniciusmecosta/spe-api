import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from app.features.devices.device_schemas import (
    UserBiometricCreate,
    UserBiometricResponse,
)


@pytest.fixture
def migration_database():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text(
            "CREATE TABLE user_biometrics (id INTEGER PRIMARY KEY, "
            "sensor_index INTEGER, finger_id INTEGER, template_data TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO user_biometrics VALUES (1, 123, 2, 'legacy'), (2, 456, 3, NULL)"
        ))
        yield connection
    engine.dispose()


def test_migration_drops_and_restores_template_column(migration_database):
    migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("010").module
    context = MigrationContext.configure(migration_database)
    with Operations.context(context):
        migration.upgrade()
        columns = migration_database.execute(text("PRAGMA table_info(user_biometrics)")).all()
        assert "template_data" not in [column[1] for column in columns]
        migration.downgrade()
        restored = migration_database.execute(text(
            "SELECT id, sensor_index, finger_id, template_data FROM user_biometrics ORDER BY id"
        )).all()
        assert restored == [(1, 123, 2, None), (2, 456, 3, None)]


def test_biometric_schema_ignores_legacy_template():
    item = UserBiometricCreate(sensor_index=123, finger_id=2, template_data="legacy")
    assert item.model_dump() == {"sensor_index": 123, "finger_id": 2}
    assert "template_data" not in UserBiometricResponse.model_fields
