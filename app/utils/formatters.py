from collections import Counter


def build_report_names(names: dict[int, str]) -> dict[int, str]:
    short_names = {user_id: format_short_name(name) for user_id, name in names.items()}
    counts = Counter(short_names.values())
    labels = {}
    used = set()
    for user_id, short_name in short_names.items():
        label = names[user_id] if counts[short_name] > 1 else short_name
        while label in used:
            label = f"{label} (ID {user_id})"
        used.add(label)
        labels[user_id] = label
    return labels


def format_short_name(full_name: str) -> str:
    if not full_name:
        return ""
    prepositions = {"de", "da", "do", "dos", "das", "e"}
    parts = full_name.split()
    filtered_parts = [p for p in parts if p.lower() not in prepositions]
    if len(filtered_parts) <= 1:
        return full_name
    return f"{filtered_parts[0]} {filtered_parts[1]}"


def mask_cnpj(c: str) -> str:
    if not c or len(c) != 14:
        return c
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def mask_cpf(c: str) -> str:
    if not c or len(c) != 11:
        return c
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


def format_name(name: str | None) -> str | None:
    if not name:
        return name
    words = name.strip().split()
    if not words:
        return name
    lowercase_words = {"de", "da", "do", "das", "dos", "e"}
    formatted_words = []
    for i, word in enumerate(words):
        word_lower = word.lower()
        if i > 0 and word_lower in lowercase_words:
            formatted_words.append(word_lower)
        else:
            formatted_words.append(word.capitalize())
    return " ".join(formatted_words)
