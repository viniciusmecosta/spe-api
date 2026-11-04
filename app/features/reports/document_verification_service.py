from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.shared.document_signature import (
    INVALID_SIGNATURE,
    JSON_MARKER,
    MAC_LENGTH,
    MISSING_SIGNATURE,
    VerificationResult,
    new_document_mac,
    verify_document,
    verify_mac,
)

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_JSON_DOCUMENT_BYTES = 256 * 1024 * 1024
READ_CHUNK_SIZE = 64 * 1024


async def _verify_json_upload(file: UploadFile, first: bytes) -> VerificationResult:
    signer = new_document_mac(b"json")
    trailer_size = len(JSON_MARKER) + MAC_LENGTH + 2
    total = len(first)
    if total > MAX_JSON_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="O JSON excede o limite de 256 MiB.")
    signer.update(first[:-trailer_size])
    tail = first[-trailer_size:]
    while True:
        chunk = await file.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_JSON_DOCUMENT_BYTES:
            raise HTTPException(status_code=413, detail="O JSON excede o limite de 256 MiB.")
        tail += chunk
        if len(tail) > trailer_size:
            signer.update(tail[:-trailer_size])
            tail = tail[-trailer_size:]
    if len(tail) != trailer_size or not tail.startswith(JSON_MARKER):
        return VerificationResult(False, MISSING_SIGNATURE)
    if not tail.endswith(b'"}'):
        return VerificationResult(False, INVALID_SIGNATURE)
    signature = tail[len(JSON_MARKER):-2]
    signer.update(b"}")
    return verify_mac(signer.hexdigest().encode("ascii"), signature)


class DocumentVerificationService:
    async def verify(self, file: UploadFile) -> dict[str, bool | str]:
        first = await file.read(READ_CHUNK_SIZE)
        if first.startswith(b"{"):
            result = await _verify_json_upload(file, first)
        else:
            content = bytearray(first)
            if len(content) > MAX_DOCUMENT_BYTES:
                raise HTTPException(status_code=413, detail="O documento excede o limite de 25 MiB.")
            while chunk := await file.read(READ_CHUNK_SIZE):
                content.extend(chunk)
                if len(content) > MAX_DOCUMENT_BYTES:
                    raise HTTPException(status_code=413, detail="O documento excede o limite de 25 MiB.")
            result = await run_in_threadpool(verify_document, bytes(content))
        return {"authentic": result.authentic, "reason": result.reason}
