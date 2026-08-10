import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.api.deps import get_current_active_user
from app.domain.models.user import User

client = TestClient(app)

def mock_get_current_active_user():
    return User(id=1, role="ADMIN")

app.dependency_overrides[get_current_active_user] = mock_get_current_active_user

@patch("app.api.v1.time_records.time_record_repository")
@patch("app.api.v1.time_records.company_repository")
@patch("app.api.v1.time_records.time_record_service")
@patch("app.api.v1.time_records.hashid_service")
def test_get_receipt(mock_hash, mock_service, mock_company, mock_repo):
    mock_hash.decode.return_value = 1
    
    class MockUser:
        name = "John Doe"
        cpf = "123.456.789-00"
        
    class MockRecord:
        id = 1
        user_id = 1
        user = MockUser()
        record_datetime = datetime(2023, 10, 27, 14, 30, 0)
        device_name = "Device"
        record_type = "ENTRY"
        
    mock_repo.get_by_id.return_value = MockRecord()
    
    class MockCompany:
        name = "Company"
        cnpj = "123"
        
    mock_company.get_current.return_value = MockCompany()
    
    class MockAuditLog:
        action = "CREATE"
        timestamp = "2023-10-27T14:30:00"
        user = MockUser()
        old_data = None
        new_data = None
        
    mock_service.get_record_timeline.return_value = [MockAuditLog()]
    
    response = client.get("/api/v1/time-records/receipt/aB3dE5")
    assert response.status_code == 200
    assert response.json()["short_id"] == "aB3dE5"
    assert response.json()["record_id"] == 1
    assert response.json()["company_name"] == "Company"

@patch("app.api.v1.time_records.time_record_repository")
@patch("app.api.v1.time_records.company_repository")
@patch("app.api.v1.time_records.receipt_service")
@patch("app.api.v1.time_records.hashid_service")
def test_get_receipt_pdf(mock_hash, mock_receipt, mock_company, mock_repo):
    mock_hash.decode.return_value = 1
    
    class MockUser:
        name = "John Doe"
        cpf = "123.456.789-00"
        
    class MockRecord:
        id = 1
        user_id = 1
        user = MockUser()
        record_datetime = datetime(2023, 10, 27, 14, 30, 0)
        device_name = "Device"
        record_type = "ENTRY"
        
    mock_repo.get_by_id.return_value = MockRecord()
    
    class MockCompany:
        name = "Company"
        cnpj = "123"
        
    mock_company.get_current.return_value = MockCompany()
    
    mock_receipt.generate_pdf_receipt.return_value = b"%PDF-1.4..."
    
    response = client.get("/api/v1/time-records/receipt/aB3dE5/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
