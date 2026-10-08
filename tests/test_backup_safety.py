import ast
import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.exceptions import InvalidTag

from scripts.apply_sql_to_postgresql import (
    _iter_sql_file_statements, apply_sql_content, apply_sql_file, restore_backup,
)
from app.features.system.backup_crypto import MAGIC, NONCE_SIZE, TAG_SIZE, decrypt_backup, encrypt_backup
from app.features.system.backup_manifest import add_manifest, validate_manifest, validate_manifest_file


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
    with pytest.raises(ValueError, match="hash"):
        validate_manifest(content.replace("VALUES (1)", "VALUES (2)"), {"users", "companies"})
    path.write_bytes(content.replace("VALUES (1)", "VALUES (2)").encode("utf-8"))
    with pytest.raises(ValueError, match="hash"):
        validate_manifest_file(path, {"users", "companies"})
    with pytest.raises(ValueError, match="sem manifesto"):
        validate_manifest("INSERT INTO users VALUES (1);", {"users"})


def test_unverified_dump_never_truncates_without_explicit_override(mocker):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = ("spe_db",)
    cursor.fetchall.side_effect = [[("alembic_version",), ("users",), ("companies",)], [("002",)]]
    mocker.patch("scripts.apply_sql_to_postgresql.get_pg_credentials", return_value={})
    mocker.patch("scripts.apply_sql_to_postgresql.connect_with_retry", return_value=connection)

    with pytest.raises(RuntimeError, match="sem manifesto"):
        apply_sql_content("INSERT INTO users (id) VALUES (1);", allow_destructive=True)

    assert not any("TRUNCATE" in str(call) for call in cursor.execute.call_args_list)
    connection.rollback.assert_called_once()


def test_row_count_mismatch_rolls_back_restore(mocker, tmp_path):
    path = tmp_path / "data.sql"
    path.write_text("INSERT INTO users (id) VALUES (1);\n", encoding="utf-8")
    add_manifest(path, {"users": 2})
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.side_effect = [("spe_db",), (1,)]
    cursor.fetchall.side_effect = [[("alembic_version",), ("users",)], [("002",)]]
    mocker.patch("scripts.apply_sql_to_postgresql.get_pg_credentials", return_value={})
    mocker.patch("scripts.apply_sql_to_postgresql.connect_with_retry", return_value=connection)

    with pytest.raises(RuntimeError, match="esperado 2, aplicado 1"):
        apply_sql_content(path.read_bytes().decode("utf-8"), allow_destructive=True)

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


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


def test_streaming_sql_splitter_handles_multiline_literals(tmp_path):
    path = tmp_path / "data.sql"
    path.write_text(
        "-- comment;\nINSERT INTO users (id, name) VALUES (1, 'a;\nb');\n"
        "INSERT INTO users (id, name) VALUES (2, 'ok');\n",
        encoding="utf-8",
    )
    statements = list(_iter_sql_file_statements(path))
    assert len(statements) == 2
    assert "'a;\nb'" in statements[0]


def test_sql_file_restore_uses_manifest_before_truncate(mocker, tmp_path):
    path = tmp_path / "partial.sql"
    path.write_text("INSERT INTO users (id) VALUES (1);\n", encoding="utf-8")
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = ("spe_db",)
    cursor.fetchall.side_effect = [[("alembic_version",), ("users",), ("companies",)], [("002",)]]
    mocker.patch("scripts.apply_sql_to_postgresql.get_pg_credentials", return_value={})
    mocker.patch("scripts.apply_sql_to_postgresql.connect_with_retry", return_value=connection)

    with pytest.raises(RuntimeError, match="sem manifesto"):
        apply_sql_file(path, allow_destructive=True)

    assert not any("TRUNCATE" in str(call) for call in cursor.execute.call_args_list)


def test_zip_restore_streams_sql_to_temporary_file(mocker, tmp_path):
    archive_path = tmp_path / "spe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("spe_dump.sql", "INSERT INTO users (id) VALUES (1);\n")
    applied = mocker.patch(
        "scripts.apply_sql_to_postgresql.apply_sql_file",
        side_effect=lambda path, **kwargs: {"path": path, "content": path.read_text()},
    )

    result = restore_backup(archive_path)

    assert "INSERT INTO users" in result["content"]
    assert not result["path"].exists()
    applied.assert_called_once()


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
        with pytest.raises(ValueError, match="inválid"):
            validate_manifest(document, set(metadata.get("row_counts", {})))
    with pytest.raises(ValueError, match="inválido"):
        validate_manifest("-- SPE-DUMP-MANIFEST: {\n", set())
