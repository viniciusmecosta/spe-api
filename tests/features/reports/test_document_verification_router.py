from fastapi.testclient import TestClient

from app.main import app
from app.shared import deps
from app.shared.document_signature import sign_pdf


def test_document_verification_requires_authentication():
    with TestClient(app) as client:
        response = client.post("/api/v1/documents/verify", files={"file": ("test.pdf", b"%PDF-test")})
    assert response.status_code == 401


def test_document_verification_accepts_manager():
    app.dependency_overrides[deps.get_current_manager] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/documents/verify",
                files={"file": ("test.pdf", sign_pdf(b"%PDF-test"), "application/pdf")},
            )
        assert response.status_code == 200
        assert response.json()["authentic"] is True
    finally:
        app.dependency_overrides.pop(deps.get_current_manager, None)
