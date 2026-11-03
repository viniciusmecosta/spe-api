import pytest
from sqlalchemy import select
from test_api_workflows import api

from app.features.system.system_models import AuditLog

__all__ = ["api"]
pytestmark = pytest.mark.asyncio


async def test_schedule_audit_preserves_states_for_create_update_delete(api, pg_session_factory):
    user_id = await api.create_employee()
    payload = {
        "valid_from": "2026-09-01", "valid_until": "2026-09-30",
        "users": [{"user_id": user_id, "schedules": [
            {
                "day_of_week": 0, "daily_minutes": 480,
                "entry_1": "08:00", "exit_1": "16:00", "is_daily_excess_enabled": True,
            },
            {
                "day_of_week": 1, "daily_minutes": 480,
                "entry_1": "08:00", "exit_1": "16:00", "is_daily_excess_enabled": True,
            },
        ]}],
    }
    await api.request("POST", "/schedules/bulk", json=payload)
    payload["users"][0]["schedules"][0]["exit_1"] = "17:00"
    payload["users"][0]["schedules"][0]["daily_minutes"] = 540
    payload["users"][0]["schedules"][1]["exit_1"] = "17:00"
    payload["users"][0]["schedules"][1]["daily_minutes"] = 540
    await api.request("PUT", "/schedules/bulk/2026-09-01/2026-09-30", json=payload)
    await api.request("DELETE", "/schedules/bulk/2026-09-01/2026-09-30")
    async with pg_session_factory() as session:
        logs = list((await session.scalars(select(AuditLog).where(
            AuditLog.entity == "USER_WORK_SCHEDULE_BULK"
        ).order_by(AuditLog.id))).all())
    assert [log.action for log in logs] == ["CREATE", "UPDATE", "DELETE"]
    created = logs[0].new_data
    before = logs[1].old_data
    after = logs[1].new_data
    deleted = logs[2].old_data
    assert "schedule_snapshot_zlib" not in created
    assert "bulk_data" not in created
    assert before["valid_from"] == after["valid_from"] == "2026-09-01"
    assert before["valid_until"] == after["valid_until"] == "2026-09-30"
    assert "Segunda e Terça: 08:00 às 16:00 (480 min; excedente: sim)" in created["schedule_summary"]
    assert before["schedule_summary"] == created["schedule_summary"]
    assert "Segunda e Terça: 08:00 às 17:00 (540 min; excedente: sim)" in after["schedule_summary"]
    assert deleted["schedule_summary"] == after["schedule_summary"]
    assert f"Funcionário Colaborador Alfa (#{user_id})" in after["schedule_summary"]
