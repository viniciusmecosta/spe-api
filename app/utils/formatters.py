def format_short_name(full_name: str) -> str:
    if not full_name:
        return ""
    parts = full_name.split()
    if len(parts) <= 1:
        return full_name
    first_name = parts[0]
    for part in parts[1:]:
        if len(part) > 2:
            return f"{first_name} {part}"
    return f"{first_name} {parts[1]}"


def get_weekday_name(weekday_idx: int, long_format: bool = False) -> str:
    days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    day = days[weekday_idx % 7]

    if long_format and day not in ["Sábado", "Domingo"]:
        return f"{day}-feira"
    return day
