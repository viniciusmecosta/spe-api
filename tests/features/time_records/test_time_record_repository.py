from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_repository import (
    AsyncTimeRecordRepository,
    TimeRecordRepository,
)
from app.features.time_records.time_record_schemas import TimeRecordUpdate
from app.shared.enums import RecordType


def test_time_record_repository(db_session, normal_user):
    repo = TimeRecordRepository()
    now = datetime.now(timezone.utc)

    r1 = repo.create(
        db_session,
        user_id=normal_user.id,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        ip_address="127.0.0.1",
        device_name="TestDevice"
    )
    assert r1.id is not None

    assert repo.get(db_session, r1.id).id == r1.id
    assert repo.get_last_by_user(db_session, normal_user.id).id == r1.id
    assert len(repo.get_all_by_user(db_session, normal_user.id)) >= 1

    by_range = repo.get_by_range(db_session, normal_user.id, now, now)
    assert len(by_range) >= 1

    by_users_range = repo.get_by_users_and_range(db_session, [normal_user.id], now, now)
    assert len(by_users_range) >= 1

    assert repo.count_unique_users_in_range(db_session, now, now) >= 1
    assert repo.count_records_in_range(db_session, now, now) >= 1

    updated = repo.update(db_session, db_obj=r1,
                          obj_in=TimeRecordUpdate(record_type=RecordType.EXIT, edit_justification="Test update"))
    assert updated.record_type == RecordType.EXIT

    tl = repo.get_timeline(db_session, r1.id)
    assert len(tl) >= 1
    assert repo.get_timeline(db_session, 99999) == []

    repo.delete(db_session, r1.id, manager_id=normal_user.id)
    assert repo.get(db_session, r1.id) is None


@pytest.mark.asyncio
async def test_async_time_record_repository(async_db_mock):
    repo = AsyncTimeRecordRepository()
    now = datetime.now(timezone.utc)
    mock_rec = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=now, is_ignored=False)

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_rec
    mock_scalars.all.return_value = [mock_rec]
    async_db_mock.scalars.return_value = mock_scalars
    async_db_mock.scalar.return_value = 1

    r1 = await repo.create(
        async_db_mock,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=now,
        ip_address="127.0.0.1",
        device_name="TestDevice"
    )
    assert r1.user_id == 1
    assert r1.device_name == "TestDevice"

    rec_get = await repo.get(async_db_mock, 1)
    assert rec_get.id == 1

    rec_last = await repo.get_last_by_user(async_db_mock, 1)
    assert rec_last.id == 1

    all_user = await repo.get_all_by_user(async_db_mock, 1)
    assert len(all_user) == 1

    by_range = await repo.get_by_range(async_db_mock, 1, now, now)
    assert len(by_range) == 1

    by_users_range = await repo.get_by_users_and_range(async_db_mock, [1], now, now)
    assert len(by_users_range) == 1

    u_count = await repo.count_unique_users_in_range(async_db_mock, now, now)
    assert u_count == 1

    r_count = await repo.count_records_in_range(async_db_mock, now, now)
    assert r_count == 1

    upd = await repo.update(async_db_mock, db_obj=mock_rec,
                            obj_in=TimeRecordUpdate(record_type=RecordType.EXIT, edit_justification="Test"))
    assert upd.id == 1

    tl = await repo.get_timeline(async_db_mock, 1)
    assert len(tl) == 1

    await repo.delete(async_db_mock, 1, manager_id=1)
    assert mock_rec.is_ignored is True
