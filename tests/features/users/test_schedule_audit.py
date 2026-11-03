import base64
import json
import zlib
from datetime import date, time
from types import SimpleNamespace

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from app.features.users.schedule_audit import (
    _decode_json_column,
    _format_clock,
    migrate_schedule_audit_logs,
    migrate_schedule_audit_payload,
    schedule_audit_data,
)


def test_schedule_audit_groups_matching_days_like_excel_without_zlib_bloat():
    mon = SimpleNamespace(
        id=1, user_id=7, day_of_week=0, daily_minutes=480,
        entry_1=time(8), exit_1=time(12), entry_2=time(14), exit_2=time(18),
        is_daily_excess_enabled=True,
    )
    tue = SimpleNamespace(
        id=2, user_id=7, day_of_week=1, daily_minutes=480,
        entry_1=time(8), exit_1=time(12), entry_2=time(14), exit_2=time(18),
        is_daily_excess_enabled=True,
    )
    wed = SimpleNamespace(
        id=3, user_id=7, day_of_week=2, daily_minutes=480,
        entry_1=time(8), exit_1=time(12), entry_2=time(14), exit_2=time(18),
        is_daily_excess_enabled=True,
    )
    sat = SimpleNamespace(
        id=4, user_id=7, day_of_week=5, daily_minutes=240,
        entry_1=time(8), exit_1=time(12, 0, 15), entry_2=None, exit_2=None,
        is_daily_excess_enabled=False,
    )
    result = schedule_audit_data([mon, tue, wed, sat], date(2026, 9, 1), date(2026, 9, 30))
    assert result == {
        "valid_from": "2026-09-01",
        "valid_until": "2026-09-30",
        "schedule_summary": (
            "Funcionário #7: Segunda a Quarta: 08:00 às 12:00 e 14:00 às 18:00 "
            "(480 min; excedente: sim); Sábado: 08:00 às 12:00:15 (240 min; excedente: não)"
        ),
    }
    assert "schedule_snapshot_zlib" not in result


def test_schedule_audit_does_not_invent_absent_hours_or_dates():
    config = SimpleNamespace(
        id=None, user_id=1, day_of_week=6, daily_minutes=0,
        entry_1=None, exit_1=None, entry_2=None, exit_2=None,
        is_daily_excess_enabled=None,
    )
    result = schedule_audit_data([config], None, None)
    assert result["valid_from"] is None
    assert result["valid_until"] is None
    assert "Domingo: sem horários informados (0 min; excedente: não informado)" in result["schedule_summary"]
    named = schedule_audit_data([config], None, None, {1: "Maria"})
    assert "Funcionário Maria (#1)" in named["schedule_summary"]


def test_schedule_audit_handles_dict_inputs_and_edge_cases():
    assert _format_clock("   ") is None
    assert _format_clock("08:30:00") == "08:30"
    assert _format_clock("08:30:45") == "08:30:45"
    assert _decode_json_column(None) is None
    assert _decode_json_column("   ") is None
    assert _decode_json_column("[1, 2]") is None
    assert _decode_json_column('{"a": 1}') == {"a": 1}
    assert migrate_schedule_audit_payload(None) is None

    dict_items = [
        {"user_id": None, "day_of_week": None, "daily_hours": 8.0, "entry_1": "08:00:00"},
        {"user_id": 2, "day_of_week": 0, "entry_1": "09:00"},
    ]
    res = schedule_audit_data(dict_items, "2026-09-01", "2026-09-30")
    assert "Funcionário não informado: Dia não informado: 08:00 às não informado (480 min)" in res["schedule_summary"]
    assert "Funcionário #2: Segunda: 09:00 às não informado" in res["schedule_summary"]


def test_migrate_schedule_audit_payload_handles_legacy_bulk_and_zlib():
    legacy_bulk = {
        "valid_from": "2026-09-01",
        "valid_until": "2026-09-30",
        "user_ids": [7],
        "bulk_data": {
            "valid_from": "2026-09-01",
            "valid_until": "2026-09-30",
            "users": [
                "invalid",
                {
                    "user_id": 7,
                    "schedules": [
                        "invalid",
                        {"day_of_week": 0, "daily_hours": 8.0, "entry_1": "08:00:00", "exit_1": "16:00:00"},
                        {"day_of_week": 1, "daily_hours": 8.0, "entry_1": "08:00:00", "exit_1": "16:00:00"},
                    ],
                },
            ],
        },
    }
    migrated = migrate_schedule_audit_payload(legacy_bulk, {7: "Carlos"})
    assert migrated == {
        "valid_from": "2026-09-01",
        "valid_until": "2026-09-30",
        "schedule_summary": "Funcionário Carlos (#7): Segunda e Terça: 08:00 às 16:00 (480 min)",
    }

    raw_snapshot = json.dumps({
        "valid_from": "2026-10-01",
        "valid_until": "2026-10-31",
        "schedules": [
            {
                "user_id": 7, "user_name": "Carlos", "day_of_week": 0, "daily_minutes": 480,
                "entry_1": "08:00:00", "exit_1": "16:00:00", "entry_2": None, "exit_2": None,
                "is_daily_excess_enabled": False,
            },
        ],
    }).encode("utf-8")
    zlib_payload = {
        "valid_from": "2026-10-01",
        "valid_until": "2026-10-31",
        "schedule_summary": "old",
        "schedule_snapshot_zlib": "v1:" + base64.b64encode(zlib.compress(raw_snapshot)).decode("ascii"),
    }
    migrated_zlib = migrate_schedule_audit_payload(zlib_payload)
    assert "schedule_snapshot_zlib" not in migrated_zlib
    assert migrated_zlib["schedule_summary"] == (
        "Funcionário Carlos (#7): Segunda: 08:00 às 16:00 (480 min; excedente: não)"
    )


def test_migration_013_compacts_history_and_reconstructs_previous_period_summary():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        migrate_schedule_audit_logs(conn)
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text(
            "CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, entity TEXT, old_data JSON, new_data JSON)"
        ))
        conn.execute(text("INSERT INTO users VALUES (5, 'Ana')"))
        create_new = json.dumps({
            "valid_from": "2026-09-01",
            "valid_until": "2026-09-30",
            "bulk_data": {
                "users": [{
                    "user_id": 5,
                    "schedules": [
                        {"day_of_week": 0, "daily_minutes": 480, "entry_1": "08:00", "exit_1": "16:00"},
                        {"day_of_week": 1, "daily_minutes": 480, "entry_1": "08:00", "exit_1": "16:00"},
                    ],
                }],
            },
        })
        update_old = json.dumps({"valid_from": "2026-09-01", "valid_until": "2026-09-30"})
        update_new = json.dumps({
            "valid_from": "2026-09-01",
            "valid_until": "2026-09-30",
            "bulk_data": {
                "users": [{
                    "user_id": 5,
                    "schedules": [
                        {"day_of_week": 0, "daily_minutes": 540, "entry_1": "08:00", "exit_1": "17:00"},
                    ],
                }],
            },
        })
        delete_old = json.dumps({"valid_from": "2026-11-01", "valid_until": "2026-11-30", "count": 2})
        conn.execute(
            text("INSERT INTO audit_logs VALUES (1, 'USER_WORK_SCHEDULE_BULK', NULL, :n1)"),
            {"n1": create_new},
        )
        conn.execute(
            text("INSERT INTO audit_logs VALUES (2, 'USER_WORK_SCHEDULE_BULK', :o2, :n2)"),
            {"o2": update_old, "n2": update_new},
        )
        conn.execute(
            text("INSERT INTO audit_logs VALUES (3, 'USER_WORK_SCHEDULE_BULK', :o3, NULL)"),
            {"o3": delete_old},
        )
        migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("013").module
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.downgrade()
        rows = conn.execute(text("SELECT id, old_data, new_data FROM audit_logs ORDER BY id")).all()
        row1_new = _decode_json_column(rows[0][2])
        row2_old = _decode_json_column(rows[1][1])
        row2_new = _decode_json_column(rows[1][2])
        row3_old = _decode_json_column(rows[2][1])
        assert row1_new["schedule_summary"] == "Funcionário Ana (#5): Segunda e Terça: 08:00 às 16:00 (480 min)"
        assert row2_old["schedule_summary"] == row1_new["schedule_summary"]
        assert row2_new["schedule_summary"] == "Funcionário Ana (#5): Segunda: 08:00 às 17:00 (540 min)"
        assert row3_old == {"valid_from": "2026-11-01", "valid_until": "2026-11-30", "count": 2}
    engine.dispose()
