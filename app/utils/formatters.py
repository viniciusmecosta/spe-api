def format_short_name(full_name: str) -> str:
    if not full_name:
        return ""
    prepositions = {"de", "da", "do", "dos", "das", "e"}
    parts = full_name.split()
    filtered_parts = [p for p in parts if p.lower() not in prepositions]
    if len(filtered_parts) <= 1:
        return full_name
    return f"{filtered_parts[0]} {filtered_parts[1]}"


def get_weekday_name(weekday_idx: int, long_format: bool = False) -> str:
    days = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    day = days[weekday_idx % 7]

    if long_format and day not in ["Sábado", "Domingo"]:
        return f"{day}-feira"
    return day
