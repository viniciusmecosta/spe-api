import ast
import hashlib
import io
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from app.features.system.backup_crypto import (
    MAGIC,
    NONCE_SIZE,
    TAG_SIZE,
    decrypt_backup,
    encrypt_backup,
)
from app.features.system.backup_manifest import (
    add_manifest,
    validate_manifest,
    validate_manifest_file,
)


def test_application_does_not_import_scripts():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module != "scripts" and not node.module.startswith("scripts."), path
            if isinstance(node, ast.Import):
                assert all(
                    name.name != "scripts" and not name.name.startswith("scripts.")
                    for name in node.names
                ), path


def test_manifest_rejects_partial_and_tampered_dumps(tmp_path):
    path = tmp_path / "data.sql"
    path.write_text("INSERT INTO users (id) VALUES (1);\n", encoding="utf-8")
    add_manifest(path, {"users": 1, "companies": 0})
    content = path.read_bytes().decode("utf-8")

    assert validate_manifest(content, {"users", "companies"}) == {
        "users": 1, "companies": 0,
    }
    assert validate_manifest_file(path, {"users", "companies"}) == {
        "users": 1, "companies": 0,
    }
    with pytest.raises(ValueError, match="não correspondem"):
        validate_manifest(content, {"users", "companies", "time_records"})
    tampered_content = content.replace("VALUES (1)", "VALUES (2)")
    with pytest.raises(ValueError, match="hash"):
        validate_manifest(tampered_content, {"users", "companies"})
    path.write_bytes(tampered_content.encode("utf-8"))
    with pytest.raises(ValueError, match="hash"):
        validate_manifest_file(path, {"users", "companies"})
    with pytest.raises(ValueError, match="sem manifesto"):
        validate_manifest("INSERT INTO users VALUES (1);", {"users"})






def test_encrypted_backup_round_trip_and_tamper_detection(tmp_path):
    source = tmp_path / "spe.zip"
    source.write_bytes(b"backup sensivel" * 100000)
    secret = "x" * 40
    encrypted = encrypt_backup(source, secret)
    source.unlink()

    restored = decrypt_backup(encrypted, secret)
    try:
        assert restored.read_bytes() == b"backup sensivel" * 100000
    finally:
        restored.unlink()

    contents = bytearray(encrypted.read_bytes())
    contents[-20] ^= 1
    encrypted.write_bytes(contents)
    with pytest.raises(InvalidTag):
        decrypt_backup(encrypted, secret)








def test_crypto_rejects_short_key_and_invalid_envelopes(tmp_path):
    source = tmp_path / "backup.zip"
    source.write_bytes(b"dados")
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_backup(source, "curta")

    encrypted = tmp_path / "backup.zip.enc"
    encrypted.write_bytes(b"incompleto")
    with pytest.raises(ValueError, match="incompleto"):
        decrypt_backup(encrypted, "x" * 40)

    encrypted.write_bytes(b"X" * (len(MAGIC) + NONCE_SIZE + TAG_SIZE))
    with pytest.raises(ValueError, match="inválido"):
        decrypt_backup(encrypted, "x" * 40)


def test_decrypt_rejects_stream_truncated_during_read(tmp_path, monkeypatch):
    source = tmp_path / "backup.zip"
    source.write_bytes(b"conteudo" * 100)
    encrypted = encrypt_backup(source, "x" * 40)
    payload = encrypted.read_bytes()
    original_open = Path.open

    class InterruptedReader(io.BytesIO):
        def read(self, size=-1):
            if self.tell() == len(MAGIC) + NONCE_SIZE and size > 0:
                return b""
            return super().read(size)

    def interrupted_open(path, mode="r", *args, **kwargs):
        if path == encrypted and mode == "rb":
            return InterruptedReader(payload)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", interrupted_open)
    with pytest.raises(ValueError, match="incompleto"):
        decrypt_backup(encrypted, "x" * 40)


def test_manifest_legacy_and_invalid_metadata(tmp_path):
    legacy = "INSERT INTO users (id) VALUES (1);\n"
    path = tmp_path / "legacy.sql"
    path.write_text(legacy, encoding="utf-8")
    assert validate_manifest(legacy, {"users"}, allow_unverified=True) is None
    assert validate_manifest_file(path, {"users"}, allow_unverified=True) is None
    with pytest.raises(ValueError, match="truncado"):
        validate_manifest("-- SPE-DUMP-MANIFEST: {}", {"users"})

    digest = hashlib.sha256(b"").hexdigest()
    cases = [
        {"version": 2, "row_counts": {}, "sha256": digest},
        {"version": 1, "row_counts": {"users": -1}, "sha256": digest},
        {"version": 1, "sha256": digest},
    ]
    for metadata in cases:
        document = "-- SPE-DUMP-MANIFEST: " + json.dumps(metadata) + "\n"
        tables = set(metadata.get("row_counts", {}))
        with pytest.raises(ValueError, match="inválid"):
            validate_manifest(document, tables)
    empty_tables = set()
    with pytest.raises(ValueError, match="inválido"):
        validate_manifest("-- SPE-DUMP-MANIFEST: {\n", empty_tables)
