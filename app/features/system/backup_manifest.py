import hashlib
import json
import os
import tempfile
from pathlib import Path

PREFIX = "-- SPE-DUMP-MANIFEST: "


def add_manifest(path: Path, row_counts: dict[str, int]) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    header = PREFIX + json.dumps(
        {"version": 1, "row_counts": row_counts, "sha256": digest.hexdigest()},
        separators=(",", ":"),
    ) + "\n"
    temporary_file = tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".manifest.tmp", dir=path.parent, delete=False,
    )
    temporary = Path(temporary_file.name)
    try:
        with temporary_file as output, path.open("rb") as source:
            output.write(header.encode("utf-8"))
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_manifest(
    content: str, expected_tables: set[str], *, allow_unverified: bool = False,
) -> dict[str, int] | None:
    header, separator, body = content.partition("\n")
    if not header.startswith(PREFIX):
        if allow_unverified:
            return None
        raise ValueError("Backup sem manifesto de integridade; use --allow-unverified-dump somente se confiar no arquivo antigo")
    if not separator:
        raise ValueError("Manifesto do backup está truncado")
    return _validate_header(header, hashlib.sha256(body.encode("utf-8")).hexdigest(), expected_tables)


def validate_manifest_file(
    path: Path, expected_tables: set[str], *, allow_unverified: bool = False,
) -> dict[str, int] | None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        header = source.readline()
        if not header.startswith(PREFIX.encode("utf-8")):
            if allow_unverified:
                return None
            raise ValueError("Backup sem manifesto de integridade; use --allow-unverified-dump somente se confiar no arquivo antigo")
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return _validate_header(header.decode("utf-8").rstrip("\r\n"), digest.hexdigest(), expected_tables)


def _validate_header(header: str, actual_digest: str, expected_tables: set[str]) -> dict[str, int]:
    try:
        manifest = json.loads(header[len(PREFIX):])
        row_counts = manifest["row_counts"]
        digest = manifest["sha256"]
        if manifest["version"] != 1 or not isinstance(row_counts, dict) or not isinstance(digest, str):
            raise ValueError("Manifesto do backup inválido")
        if set(row_counts) != expected_tables:
            raise ValueError("Tabelas do backup não correspondem ao banco de destino")
        if any(type(count) is not int or count < 0 for count in row_counts.values()):
            raise ValueError("Contagens do backup inválidas")
        if actual_digest != digest:
            raise ValueError("Backup incompleto ou alterado: hash SHA-256 não confere")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Manifesto do backup inválido") from exc
    return row_counts
