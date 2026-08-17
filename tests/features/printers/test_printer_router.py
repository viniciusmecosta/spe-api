from unittest.mock import patch

from fastapi.testclient import TestClient

import pytest
from app.features.users.user_models import User
from app.main import app
from app.shared.deps import get_current_manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_dependency():
    app.dependency_overrides[get_current_manager] = lambda: User(id=1, role="ADMIN")
    yield
    app.dependency_overrides.clear()


@patch("app.features.printers.printer_router.printer_service")
def test_read_printers(mock_service):
    mock_service.get_all.return_value = []
    response = client.get("/api/v1/printers/")
    assert response.status_code == 200
    assert response.json() == []


@patch("app.features.printers.printer_router.printer_service")
def test_read_printer(mock_service):
    class MockPrinter:
        id = 1
        name = "Test Printer"
        address = "192.168.1.50"
        status = True
        paper_width = 80
        company_id = 1

    mock_service.get_by_id.return_value = MockPrinter()
    response = client.get("/api/v1/printers/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1


@patch("app.features.printers.printer_router.printer_service")
def test_create_printer(mock_service):
    class MockPrinter:
        id = 1
        name = "Test Printer"
        address = "192.168.1.50"
        status = True
        paper_width = 80
        company_id = 1

    mock_service.create.return_value = MockPrinter()

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


@patch("app.features.printers.printer_router.printer_service")
def test_update_printer(mock_service):
    class MockPrinter:
        id = 1
        name = "Updated Printer"
        address = "192.168.1.50"
        status = True
        paper_width = 80
        company_id = 1

    mock_service.update.return_value = MockPrinter()
    response = client.patch("/api/v1/printers/1", json={"name": "Updated Printer"})
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Printer"


@patch("app.features.printers.printer_router.printer_service")
def test_delete_printer(mock_service):
    mock_service.delete.return_value = None
    response = client.delete("/api/v1/printers/1")
    assert response.status_code == 204
