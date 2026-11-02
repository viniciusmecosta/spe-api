from pathlib import Path

from app.core.config import ROOT_DIR, settings


def resolve_stored_file(stored_path: str, directory: str = '') -> Path | None:
    raw = Path(stored_path.replace('\\', '/'))
    if '..' in raw.parts:
        return None
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    allowed = (upload_root / directory).resolve()
    candidates = [raw] if raw.is_absolute() else [upload_root / raw, ROOT_DIR / raw]
    if directory and directory in raw.parts:
        index = raw.parts.index(directory)
        candidates.append(allowed.joinpath(*raw.parts[index + 1:]))
    candidates.append(allowed / raw.name)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_relative_to(allowed) and resolved.is_file():
            return resolved
    return None
