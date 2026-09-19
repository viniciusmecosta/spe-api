import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"SPEBACKUP1"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024


def _key(secret: str) -> bytes:
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("SECRET_KEY deve ter pelo menos 32 bytes para criptografar backups")
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"spe-postgresql-backup-v1",
    ).derive(secret.encode("utf-8"))


def encrypt_backup(source: Path, secret: str, destination: Path | None = None) -> Path:
    key = _key(secret)
    nonce = os.urandom(NONCE_SIZE)
    destination = destination or source.with_name(source.name + ".enc")
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    temporary_file = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False,
    )
    temporary = Path(temporary_file.name)
    try:
        with temporary_file as output, source.open("rb") as original:
            output.write(MAGIC + nonce)
            for chunk in iter(lambda: original.read(CHUNK_SIZE), b""):
                output.write(encryptor.update(chunk))
            output.write(encryptor.finalize())
            output.write(encryptor.tag)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def decrypt_backup(source: Path, secret: str) -> Path:
    key = _key(secret)
    if source.stat().st_size < len(MAGIC) + NONCE_SIZE + TAG_SIZE:
        raise ValueError("Backup criptografado incompleto")
    with source.open("rb") as encrypted:
        header = encrypted.read(len(MAGIC) + NONCE_SIZE)
        if not header.startswith(MAGIC):
            raise ValueError("Formato de backup criptografado inválido")
        encrypted.seek(-TAG_SIZE, os.SEEK_END)
        tag = encrypted.read(TAG_SIZE)
        encrypted.seek(len(MAGIC) + NONCE_SIZE)
        remaining = source.stat().st_size - len(MAGIC) - NONCE_SIZE - TAG_SIZE
        decryptor = Cipher(
            algorithms.AES(key), modes.GCM(header[len(MAGIC):], tag)
        ).decryptor()
        decryptor.authenticate_additional_data(MAGIC)
        temporary = tempfile.NamedTemporaryFile(prefix="spe-restore-", suffix=".zip", delete=False)
        target = Path(temporary.name)
        try:
            with temporary:
                while remaining:
                    chunk = encrypted.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ValueError("Backup criptografado incompleto")
                    temporary.write(decryptor.update(chunk))
                    remaining -= len(chunk)
                temporary.write(decryptor.finalize())
            return target
        except Exception:
            target.unlink(missing_ok=True)
            raise
