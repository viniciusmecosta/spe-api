from unittest.mock import MagicMock, patch

import pytest
from app.features.printers.printer_models import Printer
from app.features.time_records.receipt_service import ReceiptService


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
        "employee_pis": "123456789",
        "record_date": "27/10/2023",
        "record_time": "14:30",
        "record_type_str": "Entrada",
        "device_name": "Main Entrance",
        "nsr": 12345,
        "short_id": "aB3dE5"
    }


def test_get_escpos_printer_network(mock_printer):
    with patch('app.features.time_records.receipt_service.Network') as mock_network:
        ReceiptService._get_escpos_printer(mock_printer)
        mock_network.assert_called_once_with("192.168.1.100")


def test_get_escpos_printer_file(mock_printer):
    mock_printer.address = "/dev/usb/lp0"
    with patch('app.features.time_records.receipt_service.File') as mock_file:
        ReceiptService._get_escpos_printer(mock_printer)
        mock_file.assert_called_once_with("/dev/usb/lp0")


def test_print_escpos_receipt_success(mock_printer, receipt_data):
    mock_p = MagicMock()
    with patch('app.features.time_records.receipt_service.ReceiptService._get_escpos_printer', return_value=mock_p):
        ReceiptService._print_escpos_receipt(mock_printer, receipt_data)
        assert mock_p.set.call_count >= 2
        assert mock_p.text.call_count >= 2
        mock_p.cut.assert_called_once()
        mock_p.close.assert_called_once()


def test_print_escpos_receipt_exception(mock_printer, receipt_data):
    with patch('app.features.time_records.receipt_service.ReceiptService._get_escpos_printer',
               side_effect=Exception("Connection refused")):
        ReceiptService._print_escpos_receipt(mock_printer, receipt_data)


@pytest.mark.asyncio
async def test_print_receipt_async(mock_printer, receipt_data):
    with patch('app.features.time_records.receipt_service.ReceiptService._print_escpos_receipt') as mock_print:
        await ReceiptService.print_receipt_async(mock_printer, receipt_data)
        mock_print.assert_called_once_with(mock_printer, receipt_data)


def test_generate_pdf_receipt(receipt_data):
    pdf_bytes = ReceiptService.generate_pdf_receipt(receipt_data)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")

    na_data = receipt_data.copy()
    na_data["company_name"] = "N/A"
    na_data["company_cnpj"] = ""
    pdf_bytes_empty = ReceiptService.generate_pdf_receipt(na_data)
    assert pdf_bytes_empty.startswith(b"%PDF-")
