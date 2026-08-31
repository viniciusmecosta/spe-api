from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import pytest
from app.features.printers.printer_service import PrinterService
from app.features.users.user_models import User
from app.main import app
from app.shared.deps import get_current_manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_dependency():
    app.dependency_overrides[get_current_manager] = lambda: User(id=1, role="ADMIN")
    yield
    app.dependency_overrides.clear()


@patch.object(PrinterService, "get_all", new_callable=AsyncMock)
def test_read_printers(mock_get_all):
    mock_get_all.return_value = []
    response = client.get("/api/v1/printers/")
    assert response.status_code == 200
    assert response.json() == []


@patch.object(PrinterService, "get_by_id", new_callable=AsyncMock)
def test_read_printer(mock_get_by_id):
    class MockPrinter:
        id = 1
        name = "Test Printer"
        address = "192.168.1.50"
        status = True
        paper_width = 80
        company_id = 1

    mock_get_by_id.return_value = MockPrinter()
    response = client.get("/api/v1/printers/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1


@patch.object(PrinterService, "create", new_callable=AsyncMock)
def test_create_printer(mock_create):
    class MockPrinter:
        id = 1
        name = "Test Printer"
        address = "192.168.1.50"
        status = True
        paper_width = 80
        company_id = 1

    mock_create.return_value = MockPrinter()

    printer_data = {
        "name": "Test Printer",
        "address": "192.168.1.50",
        "status": True,
        "paper_width": 80,
        "company_id": 1,
    }
    response = client.post("/api/v1/printers/", json=printer_data)
    assert response.status_code == 201
    assert response.json()["id"] == 1


@patch.object(PrinterService, "update", new_callable=AsyncMock)
def test_update_printer(mock_update):
    class MockPrinter:
        id = 1
        name = "Updated Printer"
        address = "192.168.1.50"
        status = True
        paper_width = 80
        company_id = 1

    mock_update.return_value = MockPrinter()
    response = client.patch("/api/v1/printers/1", json={"name": "Updated Printer"})
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Printer"


@patch.object(PrinterService, "delete", new_callable=AsyncMock)
def test_delete_printer(mock_delete):
    mock_delete.return_value = None
    response = client.delete("/api/v1/printers/1")
    assert response.status_code == 204
