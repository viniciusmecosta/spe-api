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


class VerificationResult(NamedTuple):
    authentic: bool
    reason: str


def _mac(content: bytes, kind: bytes) -> bytes:
    secret = (settings.DOCUMENT_SIGNING_KEY or settings.SECRET_KEY).encode("utf-8")
    key = hmac.digest(secret, b"spe/document-signing/v1", "sha256")
    return hmac.new(key, kind + b"\0" + content, hashlib.sha256).hexdigest().encode("ascii")


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


def verify_document(content: bytes) -> VerificationResult:
    if content.startswith(b"%PDF-"):
        marker_position = len(content) - len(PDF_MARKER) - MAC_LENGTH - 1
        if marker_position < 0 or content[marker_position:marker_position + len(PDF_MARKER)] != PDF_MARKER:
            return VerificationResult(False, "Documento sem assinatura verificável.")
        payload = content[:marker_position]
        signature = content[marker_position + len(PDF_MARKER):-1]
        if content[-1:] != b"\n":
            return VerificationResult(False, "Assinatura inválida ou documento alterado.")
        expected = _mac(payload, b"pdf")
    elif content.startswith(b"PK\x03\x04"):
        comment_length = len(ZIP_MARKER) + MAC_LENGTH
        try:
            position = _zip_eocd(content, comment_length)
        except ValueError:
            return VerificationResult(False, "Documento sem assinatura verificável ou alterado.")
        comment = content[position + 22:]
        if not comment.startswith(ZIP_MARKER):
            return VerificationResult(False, "Documento sem assinatura verificável.")
        signature = comment[len(ZIP_MARKER):]
        payload = content[:position + 20] + b"\0\0"
        expected = _mac(payload, b"xlsx")
    elif content.startswith(b"{"):
        marker_position = len(content) - len(JSON_MARKER) - MAC_LENGTH - 2
        if marker_position < 0 or content[marker_position:marker_position + len(JSON_MARKER)] != JSON_MARKER:
            return VerificationResult(False, "Documento sem assinatura verificável.")
        if content[-2:] != b'"}':
            return VerificationResult(False, "Assinatura inválida ou documento alterado.")
        signature = content[marker_position + len(JSON_MARKER):-2]
        payload = content[:marker_position] + b"}"
        expected = _mac(payload, b"json")
    else:
        return VerificationResult(False, "Formato não suportado ou documento sem assinatura verificável.")
    if not re.fullmatch(rb"[0-9a-f]{64}", signature) or not hmac.compare_digest(expected, signature):
        return VerificationResult(False, "Assinatura inválida ou documento alterado.")
    return VerificationResult(True, "Assinatura válida para este sistema; o arquivo não foi alterado.")
