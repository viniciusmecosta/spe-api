from datetime import datetime, timezone

from app.features.time_records.time_record_repository import TimeRecordRepository
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
