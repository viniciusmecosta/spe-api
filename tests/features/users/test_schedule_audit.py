import base64
import json
import zlib
from datetime import date, time
from types import SimpleNamespace

from app.features.users.schedule_audit import schedule_audit_data


def test_schedule_audit_keeps_readable_and_reversible_details():
    first = SimpleNamespace(
        id=3, user_id=7, day_of_week=0, daily_minutes=481,
        entry_1=time(8), exit_1=time(12), entry_2=time(13), exit_2=time(17, 1),
        is_daily_excess_enabled=False,
    )
    second = SimpleNamespace(
        id=4, user_id=7, day_of_week=5, daily_minutes=240,
        entry_1=time(8), exit_1=None, entry_2=None, exit_2=None,
        is_daily_excess_enabled=None,
    )
    result = schedule_audit_data([first, second], date(2026, 9, 1), date(2026, 9, 30))
    assert result["valid_from"] == "2026-09-01"
    assert result["valid_until"] == "2026-09-30"
    assert "Funcionário #7" in result["schedule_summary"]
    assert "Segunda: 08:00:00–12:00:00" in result["schedule_summary"]
    assert "481 min; excedente: não" in result["schedule_summary"]
    assert "Sábado: 08:00:00–não informado" in result["schedule_summary"]
    assert "excedente: não informado" in result["schedule_summary"]
    snapshot = json.loads(zlib.decompress(base64.b64decode(result["schedule_snapshot_zlib"].removeprefix("v1:"))))
    assert snapshot["valid_from"] == "2026-09-01"
    assert snapshot["valid_until"] == "2026-09-30"
    snapshots = snapshot["schedules"]
    assert snapshots[0] == {
        "id": 3, "user_id": 7, "user_name": None, "day_of_week": 0, "daily_minutes": 481,
        "entry_1": "08:00:00", "exit_1": "12:00:00", "entry_2": "13:00:00",
        "exit_2": "17:01:00", "is_daily_excess_enabled": False,
    }
    assert snapshots[1]["exit_1"] is None


def test_schedule_audit_does_not_invent_absent_hours_or_dates():
    config = SimpleNamespace(
        id=None, user_id=1, day_of_week=6, daily_minutes=0,
        entry_1=None, exit_1=None, entry_2=None, exit_2=None,
        is_daily_excess_enabled=True,
    )
    result = schedule_audit_data([config], None, None)
    assert result["valid_from"] is None
    assert result["valid_until"] is None
    assert "Domingo: sem horários informados (0 min; excedente: sim)" in result["schedule_summary"]
    named = schedule_audit_data([config], None, None, {1: "Maria"})
    assert "Funcionário Maria (#1)" in named["schedule_summary"]
