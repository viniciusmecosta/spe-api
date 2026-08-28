from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from app.features.system.system_models import AuditLog, RoutineLog, get_local_time_naive
from app.features.system.system_repository import (
    AsyncAuditRepository,
    AsyncRoutineLogRepository,
    AuditRepository,
    RoutineLogRepository,
)
from app.features.system.system_schemas import AuditLogCreate


def test_system_models_local_time_naive():
    t = get_local_time_naive()
    assert t.tzinfo is None


def test_audit_repository(db_session, normal_user):
    repo = AuditRepository()

    created = repo.create(
        db_session,
        AuditLogCreate(
            user_id=normal_user.id,
            action="CREATE",
            entity="User",
            entity_id=normal_user.id,
            old_data=None,
            new_data={"name": "Test"}
        )
    )
    assert created.id is not None

    logs = repo.get_logs(db_session, action="CREATE", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                         order_by="asc")
    assert len(logs) >= 1

    logs_desc = repo.get_logs(db_session, order_by="desc")
    assert isinstance(logs_desc, list)


def test_routine_log_repository(db_session):
    repo = RoutineLogRepository()

    logged = repo.log_execution(
        db_session,
        routine_type="SYNC",
        status="SUCCESS",
        target_date=date(2026, 1, 1),
        details="ok"
    )
    assert logged.id is not None
    assert logged.routine_type == "SYNC"

    has_run = repo.has_routine_run_for_target_date(
        db_session,
        routine_type="SYNC",
        target_date=date(2026, 1, 1),
        status="SUCCESS"
    )
    assert has_run is True

    has_run_other = repo.has_routine_run_for_target_date(
        db_session,
        routine_type="SYNC",
        target_date=date(2026, 1, 2),
        status="SUCCESS"
    )
    assert has_run_other is False

    has_hourly = repo.has_hourly_routine_run(
        db_session,
        routine_type="SYNC",
        since_time=datetime(2020, 1, 1),
        status="SUCCESS"
    )
    assert has_hourly is True

    last_date = repo.get_last_successful_target_date(db_session, "SYNC")
    assert last_date == date(2026, 1, 1)

    logs = repo.get_logs(
        db_session,
        routine_type="SYNC",
        status="SUCCESS",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        order_by="asc"
    )
    assert isinstance(logs, list)
    assert len(logs) >= 1

    logs_desc = repo.get_logs(
        db_session,
        order_by="desc"
    )
    assert isinstance(logs_desc, list)

    del_count = repo.delete_older_than(db_session, datetime(2099, 1, 1))
    assert del_count >= 1


@pytest.mark.asyncio
async def test_async_audit_repository(async_db_mock):
    repo = AsyncAuditRepository()
    mock_log = AuditLog(id=1, action="CREATE", entity="User", entity_id=1)
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_log]
    async_db_mock.scalars.return_value = mock_scalars

    res_create = await repo.create(async_db_mock,
                                   AuditLogCreate(user_id=1, action="CREATE", entity="User", entity_id=1))
    assert res_create.action == "CREATE"

    logs = await repo.get_logs(async_db_mock, action="CREATE", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                               order_by="asc")
    assert len(logs) == 1

    logs_desc = await repo.get_logs(async_db_mock, order_by="desc")
    assert len(logs_desc) == 1


@pytest.mark.asyncio
async def test_async_routine_log_repository(async_db_mock):
    repo = AsyncRoutineLogRepository()
    mock_rlog = RoutineLog(id=1, routine_type="SYNC", status="SUCCESS", target_date=date(2026, 1, 1))
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_rlog]
    async_db_mock.scalars.return_value = mock_scalars
    async_db_mock.scalar.return_value = True

    logged = await repo.log_execution(
        async_db_mock,
        routine_type="SYNC",
        status="SUCCESS",
        target_date=date(2026, 1, 1)
    )
    assert logged.routine_type == "SYNC"

    has_run = await repo.has_routine_run_for_target_date(
        async_db_mock,
        routine_type="SYNC",
        target_date=date(2026, 1, 1)
    )
    assert has_run is True

    has_hourly = await repo.has_hourly_routine_run(
        async_db_mock,
        routine_type="SYNC",
        since_time=datetime(2026, 1, 1)
    )
    assert has_hourly is True

    async_db_mock.scalar.return_value = date(2026, 1, 1)
    last_date = await repo.get_last_successful_target_date(async_db_mock, "SYNC")
    assert last_date == date(2026, 1, 1)

    logs = await repo.get_logs(async_db_mock, routine_type="SYNC", status="SUCCESS", start_date=date(2026, 1, 1),
                               end_date=date(2026, 12, 31), order_by="asc")
    assert len(logs) == 1

    logs_desc = await repo.get_logs(async_db_mock, order_by="desc")
    assert len(logs_desc) == 1

    del_res = MagicMock()
    del_res.rowcount = 3
    async_db_mock.execute.return_value = del_res
    deleted = await repo.delete_older_than(async_db_mock, datetime(2026, 1, 1))
    assert deleted == 3
