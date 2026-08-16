from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

import pytest
from app.shared.deps import get_current_active_user
from app.shared.enums import RecordType
from app.features.time_records.time_record_schemas import ReceiptResponse
from app.features.users.user_models import User
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_dependency():
    app.dependency_overrides[get_current_active_user] = lambda: User(id=1, role="ADMIN")
    yield
    app.dependency_overrides.clear()


@patch("app.features.time_records.time_record_router.time_record_service")
def test_get_receipt(mock_service):
    mock_service.get_receipt_data.return_value = ReceiptResponse(
        short_id="aB3dE5",
        record_id=1,
        company_name="Company",
        company_cnpj="123",
        employee_name="John Doe",
        employee_cpf="123.456.789-00",
        employee_pis="123",
        record_datetime=datetime(2023, 10, 27, 14, 30, 0),
        device_name="Device",
        record_type=RecordType.ENTRY,
        timeline=[],
    )

    response = client.get("/api/v1/time-records/receipt/aB3dE5")
    assert response.status_code == 200
    assert response.json()["short_id"] == "aB3dE5"
    assert response.json()["record_id"] == 1
    assert response.json()["company_name"] == "Company"


@patch("app.features.time_records.time_record_router.time_record_service")
def test_get_receipt_pdf(mock_service):
    mock_service.get_receipt_pdf.return_value = (b"%PDF-1.4...", "1.pdf")

    response = client.get("/api/v1/time-records/receipt/aB3dE5/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="1.pdf"'
    assert response.content.startswith(b"%PDF-")

