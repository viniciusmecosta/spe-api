import secrets
from urllib.parse import quote

import pytest
from app.database.connection import postgres_connection_params
from app.database.errors import constraint_name
from app.features.time_records.time_record_schemas import (
    TimeRecordCreateAdmin,
    TimeRecordUpdate,
)
from app.features.users.user_schemas import UserUpdate


def test_uri_is_authoritative_for_backup_target():
    password = secrets.token_urlsafe(16) + "@"
    params = postgres_connection_params(
        f"postgresql+asyncpg://api:{quote(password, safe='')}@database:5432/live",
        {
            "POSTGRES_HOST": "wrong-host",
            "POSTGRES_PORT": 55439,
            "POSTGRES_DB": "wrong-database",
        },
    )
    assert params == {
        "host": "database",
        "port": 5432,
        "user": "api",
        "password": password,
        "dbname": "live",
    }


@pytest.mark.parametrize("schema", [TimeRecordCreateAdmin, TimeRecordUpdate])
def test_admin_datetimes_use_local_competence(schema):
    value = schema.model_validate(
        {
            "user_id": 1,
            "record_type": "ENTRY",
            "record_datetime": "2026-02-01T00:30:00Z",
            "edit_justification": "timezone test",
        }
    ).record_datetime
    assert value.date().isoformat() == "2026-01-31"
    assert value.hour == 21


@pytest.mark.parametrize("field", ["username", "role"])
def test_required_user_fields_distinguish_omitted_from_null(field):
    assert field not in UserUpdate().model_dump(exclude_unset=True)
    with pytest.raises(ValueError):
        UserUpdate.model_validate({field: None})


def test_constraint_name_follows_asyncpg_cause():
    cause = ValueError("duplicate")
    cause.constraint_name = "uq_payroll_closures_active_period"
    adapter = RuntimeError("driver adapter")
    adapter.__cause__ = cause
    assert constraint_name(adapter) == "uq_payroll_closures_active_period"
