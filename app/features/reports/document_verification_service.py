from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.shared.document_signature import verify_document

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


class DocumentVerificationService:
    async def verify(self, file: UploadFile) -> dict[str, bool | str]:
        content = await file.read(MAX_DOCUMENT_BYTES + 1)
        if len(content) > MAX_DOCUMENT_BYTES:
            raise HTTPException(status_code=413, detail="O documento excede o limite de 25 MiB.")
        result = await run_in_threadpool(verify_document, content)
        return {"authentic": result.authentic, "reason": result.reason}
