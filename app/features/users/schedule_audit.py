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


def _format_excess_flag(excess: Any) -> str:
    if excess is None:
        return "não informado"
    return "sim" if excess else "não"


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
        details.append(f"excedente: {_format_excess_flag(item.get('is_daily_excess_enabled'))}")
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
    snapshot = json.dumps({"schedules": normalized}, ensure_ascii=False, separators=(",", ":"))
    compressed = base64.b64encode(zlib.compress(snapshot.encode("utf-8"))).decode("ascii")
    return {
        "schedule_snapshot_zlib": f"v1:{compressed}",
        "valid_from": str(valid_from) if valid_from is not None else None,
        "valid_until": str(valid_until) if valid_until is not None else None,
        "schedule_summary": summary,
    }


