from unittest.mock import MagicMock

from fastapi import HTTPException
from sqlalchemy.orm import Session

import pytest
from app.features.printers.printer_models import Printer
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate
from app.features.printers.printer_service import printer_service


def test_printer_service_get_by_id_success(mocker):
    mock_db = MagicMock(spec=Session)
    mock_printer = Printer(id=1, name="Printer 1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.printer_repository.get_by_id", return_value=mock_printer)

    result = printer_service.get_by_id(mock_db, 1)
    assert result == mock_printer


def test_printer_service_get_by_id_not_found(mocker):
    mock_db = MagicMock(spec=Session)
    mocker.patch("app.features.printers.printer_service.printer_repository.get_by_id", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        printer_service.get_by_id(mock_db, 999)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Impressora não encontrada."


def test_printer_service_get_all(mocker):
    mock_db = MagicMock(spec=Session)
    mock_printers = [Printer(id=1, name="P1", address="192.168.1.10", company_id=1)]
    mocker.patch("app.features.printers.printer_service.printer_repository.get_all", return_value=mock_printers)

    result = printer_service.get_all(mock_db, skip=0, limit=10)
    assert result == mock_printers


def test_printer_service_create(mocker):
    mock_db = MagicMock(spec=Session)
    printer_in = PrinterCreate(name="P1", address="192.168.1.10", company_id=1)
    mock_printer = Printer(id=1, name="P1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.printer_repository.create", return_value=mock_printer)
    mocker.patch("app.features.printers.printer_service.audit_service.log_change")

    result = printer_service.create(mock_db, printer_in, current_user_id=1)
    assert result == mock_printer


def test_printer_service_update(mocker):
    mock_db = MagicMock(spec=Session)
    printer_update = PrinterUpdate(name="Updated P1")
    mock_printer = Printer(id=1, name="Updated P1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.printer_repository.get_by_id", return_value=mock_printer)
    mocker.patch("app.features.printers.printer_service.printer_repository.update", return_value=mock_printer)
    mocker.patch("app.features.printers.printer_service.serialize_model", return_value={})
    mocker.patch("app.features.printers.printer_service.audit_service.log_change")

    result = printer_service.update(mock_db, 1, printer_update, current_user_id=1)
    assert result == mock_printer


def test_printer_service_delete(mocker):
    mock_db = MagicMock(spec=Session)
    mock_printer = Printer(id=1, name="P1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.printer_repository.get_by_id", return_value=mock_printer)
    mock_delete = mocker.patch("app.features.printers.printer_service.printer_repository.delete")
    mocker.patch("app.features.printers.printer_service.audit_service.log_change")

    printer_service.delete(mock_db, 1, current_user_id=1)
    mock_delete.assert_called_once_with(mock_db, printer_id=1)
