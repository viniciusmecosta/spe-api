import base64
import json
import zlib
from collections import defaultdict

from fastapi.encoders import jsonable_encoder

from app.shared.enums import DayOfWeek


def schedule_audit_data(configs, valid_from, valid_until, names=None):
    names = names or {}
    snapshots = []
    for config in configs:
        snapshots.append({
            "id": config.id,
            "user_id": config.user_id,
            "user_name": names.get(config.user_id),
            "day_of_week": config.day_of_week,
            "daily_minutes": config.daily_minutes,
            "entry_1": config.entry_1,
            "exit_1": config.exit_1,
            "entry_2": config.entry_2,
            "exit_2": config.exit_2,
            "is_daily_excess_enabled": config.is_daily_excess_enabled,
        })
    snapshots = jsonable_encoder(snapshots)
    grouped = defaultdict(list)
    for item in snapshots:
        periods = []
        for number in (1, 2):
            entry = item[f"entry_{number}"]
            exit_time = item[f"exit_{number}"]
            if entry is not None or exit_time is not None:
                periods.append(f"{entry or 'não informado'}–{exit_time or 'não informado'}")
        hours = ", ".join(periods) if periods else "sem horários informados"
        excess = item["is_daily_excess_enabled"]
        excess_text = "não informado" if excess is None else "sim" if excess else "não"
        grouped[item["user_id"]].append(
            f"{DayOfWeek(item['day_of_week']).abreviado}: {hours} "
            f"({item['daily_minutes']} min; excedente: {excess_text})"
        )
    summary = "\n".join(
        f"Funcionário {names[user_id]} (#{user_id}): {'; '.join(days)}"
        if names.get(user_id) else f"Funcionário #{user_id}: {'; '.join(days)}"
        for user_id, days in sorted(grouped.items())
    )
    snapshot = {
        "valid_from": str(valid_from) if valid_from is not None else None,
        "valid_until": str(valid_until) if valid_until is not None else None,
        "schedules": snapshots,
    }
    raw = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "valid_from": str(valid_from) if valid_from is not None else None,
        "valid_until": str(valid_until) if valid_until is not None else None,
        "schedule_summary": summary,
        "schedule_snapshot_zlib": "v1:" + base64.b64encode(zlib.compress(raw)).decode("ascii"),
    }
