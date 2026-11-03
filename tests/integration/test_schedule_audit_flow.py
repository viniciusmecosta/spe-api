import base64
import json
import zlib

import pytest
from sqlalchemy import select
from test_api_workflows import api

from app.features.system.system_models import AuditLog

__all__ = ["api"]
pytestmark = pytest.mark.asyncio


def unpack(data):
    return json.loads(zlib.decompress(base64.b64decode(data["schedule_snapshot_zlib"].removeprefix("v1:"))))


async def test_schedule_audit_preserves_states_for_create_update_delete(api, pg_session_factory):
    user_id = await api.create_employee()
    payload = {
        "valid_from": "2026-09-01", "valid_until": "2026-09-30",
        "users": [{"user_id": user_id, "schedules": [{
            "day_of_week": 1, "daily_minutes": 480,
            "entry_1": "08:00", "exit_1": "16:00", "is_daily_excess_enabled": True,
        }]}],
    }
    await api.request("POST", "/schedules/bulk", json=payload)
    payload["users"][0]["schedules"][0]["exit_1"] = "17:00"
    payload["users"][0]["schedules"][0]["daily_minutes"] = 540
    await api.request("PUT", "/schedules/bulk/2026-09-01/2026-09-30", json=payload)
    await api.request("DELETE", "/schedules/bulk/2026-09-01/2026-09-30")
    async with pg_session_factory() as session:
        logs = list((await session.scalars(select(AuditLog).where(
            AuditLog.entity == "USER_WORK_SCHEDULE_BULK"
        ).order_by(AuditLog.id))).all())
    assert [log.action for log in logs] == ["CREATE", "UPDATE", "DELETE"]
    created = unpack(logs[0].new_data)
    before = unpack(logs[1].old_data)
    after = unpack(logs[1].new_data)
    deleted = unpack(logs[2].old_data)
    assert created["schedules"][0]["daily_minutes"] == 480
    assert created["schedules"][0]["id"] == before["schedules"][0]["id"]
    assert before["schedules"][0]["exit_1"] == "16:00:00"
    assert after["schedules"][0]["exit_1"] == "17:00:00"
    assert deleted["schedules"][0]["daily_minutes"] == 540
    assert before["valid_from"] == after["valid_from"] == "2026-09-01"
    assert f"Funcionário Colaborador Alfa (#{user_id})" in logs[1].new_data["schedule_summary"]
