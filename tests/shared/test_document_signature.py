import io
import json

import pytest
from openpyxl import Workbook, load_workbook
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.shared.document_signature import (
    sign_json,
    sign_pdf,
    sign_xlsx,
    verify_document,
)


@pytest.fixture
def signing_key(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_SIGNING_KEY", "test-signing-key")


def pdf_bytes():
    stream = io.BytesIO()
    document = canvas.Canvas(stream)
    document.drawString(10, 10, "Documento")
    document.save()
    return stream.getvalue()


def xlsx_bytes():
    stream = io.BytesIO()
    workbook = Workbook()
    workbook.active["A1"] = "Documento"
    workbook.save(stream)
    return stream.getvalue()


@pytest.mark.usefixtures("signing_key")
@pytest.mark.parametrize("factory,sign", [(pdf_bytes, sign_pdf), (xlsx_bytes, sign_xlsx), (lambda: b'{"id":1}', sign_json)])
def test_document_signature_detects_changes(factory, sign, monkeypatch):
    original = factory()
    signed = sign(original)
    assert verify_document(signed).authentic
    modified = bytearray(signed)
    modified[12] ^= 1
    assert not verify_document(bytes(modified)).authentic
    assert not verify_document(signed + b"x").authentic
    monkeypatch.setattr(settings, "DOCUMENT_SIGNING_KEY", "different-key")
    assert not verify_document(signed).authentic


@pytest.mark.usefixtures("signing_key")
def test_signed_xlsx_is_readable():
    workbook = load_workbook(io.BytesIO(sign_xlsx(xlsx_bytes())))
    assert workbook.active["A1"].value == "Documento"


@pytest.mark.usefixtures("signing_key")
def test_signed_json_is_readable():
    content = sign_json(b'{"id":1}')
    assert json.loads(content)["id"] == 1


@pytest.mark.parametrize("content", [b"", b"other", b"%PDF-1.4", b"PK\x03\x04", b"{}"])
def test_unsigned_or_unsupported_files_are_not_authentic(content):
    assert not verify_document(content).authentic


def test_invalid_signing_inputs_are_rejected():
    with pytest.raises(ValueError):
        sign_pdf(b"other")
    with pytest.raises(ValueError):
        sign_xlsx(b"other")
    with pytest.raises(ValueError):
        sign_json(b"[]")


def test_rejects_malformed_signature_containers():
    pdf = sign_pdf(pdf_bytes())
    assert not verify_document(pdf[:-1] + b"x").authentic

    xlsx = sign_xlsx(xlsx_bytes())
    marker = b"SPE-HMAC-SHA256-V1:"
    position = xlsx.rfind(marker)
    assert not verify_document(xlsx[:position] + b"X" + xlsx[position + 1:]).authentic

    document = sign_json(b'{"id":1}')
    assert not verify_document(document[:-1] + b"x").authentic
    assert not verify_document(document[:-3] + b"z" + document[-2:]).authentic

    unsigned = xlsx_bytes()
    with pytest.raises(ValueError):
        sign_xlsx(unsigned[:-2] + b"\x01\x00")
