from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_current_active_user
from app.domain.models.user import User
from unittest.mock import patch

client = TestClient(app)

def mock_get_current_active_user():
    return User(id=1, role="ADMIN")

app.dependency_overrides[get_current_active_user] = mock_get_current_active_user

@patch("app.api.v1.printers.printer_repository")
def test_read_printers(mock_repo):
    mock_repo.get_all.return_value = []
    response = client.get("/api/v1/printers/")
    assert response.status_code == 200
    assert response.json() == []

@patch("app.api.v1.printers.printer_repository")
def test_create_printer(mock_repo):
    class MockPrinter:
        id = 1
        name = "Test Printer"
        address = "192.168.1.50"
        status = True
        paper_width = 80
        company_id = 1
        
    mock_repo.create.return_value = MockPrinter()
    
    printer_data = {
        "name": "Test Printer",
        "address": "192.168.1.50",
        "status": True,
        "paper_width": 80,
        "company_id": 1
    }
    response = client.post("/api/v1/printers/", json=printer_data)
    assert response.status_code == 201
    assert response.json()["id"] == 1
