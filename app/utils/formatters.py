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
