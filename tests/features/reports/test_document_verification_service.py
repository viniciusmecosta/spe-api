from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.features.reports.document_verification_service import (
    MAX_DOCUMENT_BYTES,
    DocumentVerificationService,
)
from app.shared.document_signature import sign_pdf


async def test_verifies_signed_and_unsigned_uploads():
    service = DocumentVerificationService()
    valid = await service.verify(UploadFile(file=BytesIO(sign_pdf(b"%PDF-test")), filename="document.pdf"))
    invalid = await service.verify(UploadFile(file=BytesIO(b"unsigned"), filename="document.pdf"))
    assert valid["authentic"] is True
    assert invalid["authentic"] is False


async def test_rejects_oversized_upload():
    service = DocumentVerificationService()
    with pytest.raises(HTTPException) as error:
        await service.verify(UploadFile(file=BytesIO(b"x" * (MAX_DOCUMENT_BYTES + 1)), filename="large.pdf"))
    assert error.value.status_code == 413
