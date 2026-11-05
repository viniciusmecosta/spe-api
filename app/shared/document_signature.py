import hashlib
import hmac
import re
import struct
from typing import NamedTuple

from app.core.config import settings

PDF_MARKER = b"\n% SPE-HMAC-SHA256-V1:"
ZIP_MARKER = b"SPE-HMAC-SHA256-V1:"
ZIP_EOCD = b"PK\x05\x06"
JSON_MARKER = b',"assinatura_spe":"hmac-sha256-v1:'
MAC_LENGTH = 64
MISSING_SIGNATURE = "Documento sem assinatura verificável."
INVALID_SIGNATURE = "Assinatura inválida ou documento alterado."
VALID_SIGNATURE = "Assinatura válida para este sistema; o arquivo não foi alterado."


class VerificationResult(NamedTuple):
    authentic: bool
    reason: str


def new_document_mac(kind: bytes) -> hmac.HMAC:
    secret = (settings.DOCUMENT_SIGNING_KEY or settings.SECRET_KEY).encode("utf-8")
    key = hmac.digest(secret, b"spe/document-signing/v1", "sha256")
    return hmac.new(key, kind + b"\0", hashlib.sha256)


def _mac(content: bytes, kind: bytes) -> bytes:
    signer = new_document_mac(kind)
    signer.update(content)
    return signer.hexdigest().encode("ascii")


def sign_pdf(content: bytes) -> bytes:
    if not content.startswith(b"%PDF-"):
        raise ValueError("PDF inválido")
    return content + PDF_MARKER + _mac(content, b"pdf") + b"\n"


def _zip_eocd(content: bytes, comment_length: int) -> int:
    position = len(content) - 22 - comment_length
    if position < 0 or content[position:position + 4] != ZIP_EOCD:
        raise ValueError("Arquivo ZIP inválido")
    if struct.unpack_from("<H", content, position + 20)[0] != comment_length:
        raise ValueError("Comentário ZIP inválido")
    return position


def sign_xlsx(content: bytes) -> bytes:
    position = _zip_eocd(content, 0)
    signature = ZIP_MARKER + _mac(content, b"xlsx")
    return content[:position + 20] + struct.pack("<H", len(signature)) + signature


def sign_json(content: bytes) -> bytes:
    if not content.startswith(b"{") or not content.endswith(b"}"):
        raise ValueError("JSON inválido")
    return content[:-1] + JSON_MARKER + _mac(content, b"json") + b'"}'


def verify_mac(expected: bytes, signature: bytes) -> VerificationResult:
    if not re.fullmatch(rb"[0-9a-f]{64}", signature) or not hmac.compare_digest(expected, signature):
        return VerificationResult(False, INVALID_SIGNATURE)
    return VerificationResult(True, VALID_SIGNATURE)


def _verify_pdf(content: bytes) -> VerificationResult:
    position = len(content) - len(PDF_MARKER) - MAC_LENGTH - 1
    if position < 0 or content[position:position + len(PDF_MARKER)] != PDF_MARKER:
        return VerificationResult(False, MISSING_SIGNATURE)
    if content[-1:] != b"\n":
        return VerificationResult(False, INVALID_SIGNATURE)
    return verify_mac(_mac(content[:position], b"pdf"), content[position + len(PDF_MARKER):-1])


def _verify_xlsx(content: bytes) -> VerificationResult:
    try:
        position = _zip_eocd(content, len(ZIP_MARKER) + MAC_LENGTH)
    except ValueError:
        return VerificationResult(False, "Documento sem assinatura verificável ou alterado.")
    comment = content[position + 22:]
    if not comment.startswith(ZIP_MARKER):
        return VerificationResult(False, MISSING_SIGNATURE)
    payload = content[:position + 20] + b"\0\0"
    return verify_mac(_mac(payload, b"xlsx"), comment[len(ZIP_MARKER):])


def _verify_json(content: bytes) -> VerificationResult:
    position = len(content) - len(JSON_MARKER) - MAC_LENGTH - 2
    if position < 0 or content[position:position + len(JSON_MARKER)] != JSON_MARKER:
        return VerificationResult(False, MISSING_SIGNATURE)
    if content[-2:] != b'"}':
        return VerificationResult(False, INVALID_SIGNATURE)
    return verify_mac(_mac(content[:position] + b"}", b"json"), content[position + len(JSON_MARKER):-2])


def verify_document(content: bytes) -> VerificationResult:
    if content.startswith(b"%PDF-"):
        return _verify_pdf(content)
    if content.startswith(b"PK\x03\x04"):
        return _verify_xlsx(content)
    if content.startswith(b"{"):
        return _verify_json(content)
    return VerificationResult(False, "Formato não suportado ou documento sem assinatura verificável.")
