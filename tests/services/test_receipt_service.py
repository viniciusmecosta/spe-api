from unittest.mock import MagicMock, patch

import pytest
from app.services.receipt_service import ReceiptService
from app.domain.models.printer import Printer


@pytest.fixture
def mock_printer():
    printer = Printer(id=1, name="Test Printer", address="192.168.1.100", status=True, paper_width=80, company_id=1)
    return printer


@pytest.fixture
def receipt_data():
    return {
        "company_name": "Test Company",
        "company_cnpj": "12.345.678/0001-99",
        "employee_name": "John Doe",
        "employee_cpf": "123.456.789-00",
        "record_datetime": "2023-10-27 14:30:00",
        "device_name": "Main Entrance",
        "nsr": 12345,
        "short_id": "aB3dE5"
    }


def test_get_escpos_printer_network(mock_printer):
    with patch('app.services.receipt_service.Network') as mock_network:
        ReceiptService._get_escpos_printer(mock_printer)
        mock_network.assert_called_once_with("192.168.1.100")


def test_get_escpos_printer_file(mock_printer):
    mock_printer.address = "/dev/usb/lp0"
    with patch('app.services.receipt_service.File') as mock_file:
        ReceiptService._get_escpos_printer(mock_printer)
        mock_file.assert_called_once_with("/dev/usb/lp0")


@pytest.mark.asyncio
async def test_print_receipt_async(mock_printer, receipt_data):
    with patch('app.services.receipt_service.ReceiptService._print_escpos_receipt') as mock_print:
        await ReceiptService.print_receipt_async(mock_printer, receipt_data)
        mock_print.assert_called_once_with(mock_printer, receipt_data)


def test_generate_pdf_receipt(receipt_data):
    pdf_bytes = ReceiptService.generate_pdf_receipt(receipt_data)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
