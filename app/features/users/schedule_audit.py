import base64
import json
import zlib
from collections import defaultdict
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.shared.schedule_report_service import format_day_groups


def _format_clock(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.endswith(":00"):
        return text[:5]
    return text


def _extract_daily_minutes(item: dict[str, Any]) -> int | None:
    daily_minutes = item.get("daily_minutes")
    if daily_minutes is not None:
        return int(daily_minutes)
    daily_hours = item.get("daily_hours")
    if daily_hours is not None:
        return round(float(daily_hours) * 60)
    return None


def _format_schedule_descriptor(item: dict[str, Any]) -> str:
    periods = []
    for number in (1, 2):
        entry = _format_clock(item.get(f"entry_{number}"))
        exit_time = _format_clock(item.get(f"exit_{number}"))
        if entry is not None or exit_time is not None:
            periods.append(f"{entry or 'não informado'} às {exit_time or 'não informado'}")
    hours = " e ".join(periods) if periods else "sem horários informados"
    details = []
    daily_minutes = _extract_daily_minutes(item)
    if daily_minutes is not None:
        details.append(f"{daily_minutes} min")
    if item.get("_has_excess", True):
        excess = item.get("is_daily_excess_enabled")
        excess_text = "não informado" if excess is None else "sim" if excess else "não"
        details.append(f"excedente: {excess_text}")
    suffix = f" ({'; '.join(details)})" if details else ""
    return f"{hours}{suffix}"


def _normalize_config(config: Any, names: dict[int, str]) -> dict[str, Any]:
    if isinstance(config, dict):
        user_id = config.get("user_id")
        return {
            "user_id": user_id,
            "user_name": config.get("user_name") or (names.get(user_id) if user_id is not None else None),
            "day_of_week": config.get("day_of_week"),
            "daily_minutes": _extract_daily_minutes(config),
            "entry_1": config.get("entry_1"),
            "exit_1": config.get("exit_1"),
            "entry_2": config.get("entry_2"),
            "exit_2": config.get("exit_2"),
            "is_daily_excess_enabled": config.get("is_daily_excess_enabled"),
            "_has_excess": "is_daily_excess_enabled" in config,
        }
    return {
        "user_id": config.user_id,
        "user_name": names.get(config.user_id),
        "day_of_week": config.day_of_week,
        "daily_minutes": getattr(config, "daily_minutes", None),
        "daily_hours": getattr(config, "daily_hours", None),
        "entry_1": config.entry_1,
        "exit_1": config.exit_1,
        "entry_2": config.entry_2,
        "exit_2": config.exit_2,
        "is_daily_excess_enabled": getattr(config, "is_daily_excess_enabled", None),
        "_has_excess": True,
    }


def _format_user_line(user_id: Any, user_name: str | None, user_items: list[dict[str, Any]]) -> str:
    days_by_descriptor: dict[str, list[int]] = defaultdict(list)
    ordered = sorted(
        user_items,
        key=lambda item: item["day_of_week"] if isinstance(item.get("day_of_week"), int) else 99,
    )
    for item in ordered:
        day = item.get("day_of_week")
        descriptor = _format_schedule_descriptor(item)
        if isinstance(day, int) and 0 <= day <= 6:
            days_by_descriptor[descriptor].append(day)
        else:
            days_by_descriptor[descriptor].append(-1)
    groups = []
    for descriptor, days in days_by_descriptor.items():
        valid_days = [day for day in days if day >= 0]
        day_label = format_day_groups(valid_days) if valid_days else "Dia não informado"
        groups.append(f"{day_label}: {descriptor}")
    if user_name:
        return f"Funcionário {user_name} (#{user_id}): {'; '.join(groups)}"
    if user_id is not None:
        return f"Funcionário #{user_id}: {'; '.join(groups)}"
    return f"Funcionário não informado: {'; '.join(groups)}"


def schedule_audit_data(configs, valid_from, valid_until, names=None):
    resolved_names = names or {}
    normalized = jsonable_encoder([_normalize_config(config, resolved_names) for config in configs])
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    user_names: dict[Any, str | None] = {}
    for item in normalized:
        uid = item.get("user_id")
        grouped[uid].append(item)
        if item.get("user_name") and not user_names.get(uid):
            user_names[uid] = item["user_name"]
    summary = "\n".join(
        _format_user_line(
            user_id,
            user_names.get(user_id) or resolved_names.get(user_id),
            days,
        )
        for user_id, days in sorted(grouped.items(), key=lambda pair: (pair[0] is None, pair[0]))
    )
    return {
        "valid_from": str(valid_from) if valid_from is not None else None,
        "valid_until": str(valid_until) if valid_until is not None else None,
        "schedule_summary": summary,
    }


def _extract_legacy_configs(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    snapshot_zlib = payload.get("schedule_snapshot_zlib")
    if isinstance(snapshot_zlib, str) and snapshot_zlib.startswith("v1:"):
        raw = zlib.decompress(base64.b64decode(snapshot_zlib.removeprefix("v1:")))
        unpacked = json.loads(raw.decode("utf-8"))
        schedules = unpacked.get("schedules")
        if isinstance(schedules, list):
            return [item for item in schedules if isinstance(item, dict)]
    bulk = payload.get("bulk_data")
    if isinstance(bulk, dict) and isinstance(bulk.get("users"), list):
        extracted: list[dict[str, Any]] = []
        for user_entry in bulk["users"]:
            if not isinstance(user_entry, dict) or not isinstance(user_entry.get("schedules"), list):
                continue
            uid = user_entry.get("user_id")
            uname = user_entry.get("user_name")
            for schedule in user_entry["schedules"]:
                if isinstance(schedule, dict):
                    extracted.append({**schedule, "user_id": uid, "user_name": uname})
        return extracted
    return None


def migrate_schedule_audit_payload(
    payload: dict[str, Any] | None,
    names: dict[int, str] | None = None,
    fallback_summary: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload
    resolved_names = names or {}
    bulk = payload.get("bulk_data") if isinstance(payload.get("bulk_data"), dict) else {}
    valid_from = payload.get("valid_from") or bulk.get("valid_from")
    valid_until = payload.get("valid_until") or bulk.get("valid_until")
    configs = _extract_legacy_configs(payload)
    if configs is not None:
        return schedule_audit_data(configs, valid_from, valid_until, resolved_names)
    cleaned = {
        key: value
        for key, value in payload.items()
        if key not in {"bulk_data", "schedule_snapshot_zlib", "schedule_snapshot_format", "user_ids"}
    }
    if not cleaned.get("schedule_summary") and fallback_summary:
        cleaned["schedule_summary"] = fallback_summary
    return cleaned


def _decode_json_column(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return None


def migrate_schedule_audit_logs(connection: Any) -> None:
    import sqlalchemy as sa

    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    if "audit_logs" not in tables:
        return
    names: dict[int, str] = {}
    if "users" in tables:
        user_rows = connection.execute(sa.text("SELECT id, name FROM users")).all()
        names = {int(row[0]): str(row[1]) for row in user_rows if row[0] is not None and row[1]}
    audit_table = sa.table(
        "audit_logs",
        sa.column("id", sa.Integer),
        sa.column("entity", sa.String),
        sa.column("old_data", sa.JSON),
        sa.column("new_data", sa.JSON),
    )
    rows = connection.execute(
        sa.select(audit_table.c.id, audit_table.c.old_data, audit_table.c.new_data)
        .where(
            audit_table.c.entity.in_(
                ["USER_WORK_SCHEDULE_BULK", "USER_WORK_SCHEDULE_CONFIGS", "USER_WORK_SCHEDULE"]
            )
        )
        .order_by(audit_table.c.id.asc())
    ).all()
    last_summary_by_period: dict[tuple[str, str], str] = {}
    for row_id, raw_old, raw_new in rows:
        old_data = _decode_json_column(raw_old)
        new_data = _decode_json_column(raw_new)
        fallback_old = None
        if isinstance(old_data, dict):
            old_vf = old_data.get("valid_from")
            old_vu = old_data.get("valid_until")
            if old_vf and old_vu:
                fallback_old = last_summary_by_period.get((str(old_vf), str(old_vu)))
        migrated_old = migrate_schedule_audit_payload(old_data, names, fallback_old)
        migrated_new = migrate_schedule_audit_payload(new_data, names)
        if isinstance(migrated_new, dict):
            new_vf = migrated_new.get("valid_from")
            new_vu = migrated_new.get("valid_until")
            new_summary = migrated_new.get("schedule_summary")
            if new_vf and new_vu and new_summary:
                last_summary_by_period[(str(new_vf), str(new_vu))] = str(new_summary)
        if migrated_old != old_data or migrated_new != new_data:
            connection.execute(
                audit_table.update()
                .where(audit_table.c.id == row_id)
                .values(old_data=migrated_old, new_data=migrated_new)
            )

