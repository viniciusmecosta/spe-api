from datetime import date

from app.features.system.system_models import get_local_time_naive
from app.features.system.system_repository import AuditRepository, RoutineLogRepository
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

    manual = repo.get_manual_changes(db_session, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                                     order_by="asc")
    assert len(manual) >= 1

    manual_desc = repo.get_manual_changes(db_session, order_by="desc")
    assert isinstance(manual_desc, list)


def test_routine_log_repository(db_session):
    repo = RoutineLogRepository()

    logs = repo.get_logs(
        db_session,
        routine_type="SYNC",
        status="SUCCESS",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        order_by="asc"
    )
    assert isinstance(logs, list)

    logs_desc = repo.get_logs(
        db_session,
        order_by="desc"
    )
    assert isinstance(logs_desc, list)
