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
    upload = UploadFile(file=BytesIO(b"x" * (MAX_DOCUMENT_BYTES + 1)), filename="large.pdf")
    with pytest.raises(HTTPException) as error:
        await service.verify(upload)
    assert error.value.status_code == 413


async def test_verifies_large_json_in_chunks_and_rejects_tampering(monkeypatch):
    from app.features.reports import document_verification_service as module
    from app.shared.document_signature import sign_json

    monkeypatch.setattr(module, "READ_CHUNK_SIZE", 32)
    data = b'{"records":"' + b"x" * 500 + b'"}'
    signed = sign_json(data)
    service = DocumentVerificationService()
    valid_file = UploadFile(file=BytesIO(signed), filename="document.json")
    bad_file = UploadFile(file=BytesIO(signed.replace(b"xxxx", b"xxxy", 1)), filename="document.json")
    valid = await service.verify(valid_file)
    invalid = await service.verify(bad_file)
    assert valid["authentic"] is True
    assert invalid["authentic"] is False


async def test_json_and_binary_limits_are_independent(monkeypatch):
    from app.features.reports import document_verification_service as module

    monkeypatch.setattr(module, "MAX_JSON_DOCUMENT_BYTES", 128)
    monkeypatch.setattr(module, "MAX_DOCUMENT_BYTES", 32)
    monkeypatch.setattr(module, "READ_CHUNK_SIZE", 16)
    service = DocumentVerificationService()
    allowed_json = UploadFile(file=BytesIO(b"{" + b"x" * 80), filename="document.json")
    too_large_json = UploadFile(file=BytesIO(b"{" + b"x" * 128), filename="large.json")
    too_large_binary = UploadFile(file=BytesIO(b"%PDF-" + b"x" * 28), filename="large.pdf")
    assert (await service.verify(allowed_json))["authentic"] is False
    with pytest.raises(HTTPException) as json_error:
        await service.verify(too_large_json)
    assert json_error.value.status_code == 413
    with pytest.raises(HTTPException) as binary_error:
        await service.verify(too_large_binary)
    assert binary_error.value.status_code == 413


async def test_malformed_json_trailer_reports_why():
    from app.shared.document_signature import sign_json

    signed = sign_json(b'{"value":1}')
    service = DocumentVerificationService()
    unsigned = UploadFile(file=BytesIO(b'{"value":1}'), filename="unsigned.json")
    malformed = UploadFile(file=BytesIO(signed[:-1] + b"X"), filename="bad.json")
    assert (await service.verify(unsigned))["authentic"] is False
    assert (await service.verify(malformed))["reason"] == "Assinatura inválida ou documento alterado."


@pytest.mark.parametrize("content", [b'{"value":1}', b"%PDF-test"])
async def test_rejects_first_chunk_exceeding_limit(monkeypatch, content):
    from app.features.reports import document_verification_service as module

    monkeypatch.setattr(module, "MAX_JSON_DOCUMENT_BYTES", 4)
    monkeypatch.setattr(module, "MAX_DOCUMENT_BYTES", 4)
    upload = UploadFile(file=BytesIO(content), filename="document")
    service = DocumentVerificationService()
    with pytest.raises(HTTPException) as error:
        await service.verify(upload)
    assert error.value.status_code == 413
