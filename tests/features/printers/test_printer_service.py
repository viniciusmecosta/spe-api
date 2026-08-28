from unittest.mock import AsyncMock

import pytest
from app.features.printers.printer_exceptions import PrinterNotFoundError
from app.features.printers.printer_models import Printer
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate
from app.features.printers.printer_service import printer_service


@pytest.mark.asyncio
async def test_printer_service_get_by_id_success(async_db_mock, mocker):
    mock_printer = Printer(id=1, name="Printer 1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.async_printer_repository.get_by_id", new_callable=AsyncMock,
                 return_value=mock_printer)

    result = await printer_service.get_by_id(async_db_mock, 1)
    assert result == mock_printer


@pytest.mark.asyncio
async def test_printer_service_get_by_id_not_found(async_db_mock, mocker):
    mocker.patch("app.features.printers.printer_service.async_printer_repository.get_by_id", new_callable=AsyncMock,
                 return_value=None)

    with pytest.raises(PrinterNotFoundError) as exc_info:
        await printer_service.get_by_id(async_db_mock, 999)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Impressora de ID 999 não encontrada."


@pytest.mark.asyncio
async def test_printer_service_get_all(async_db_mock, mocker):
    mock_printers = [Printer(id=1, name="P1", address="192.168.1.10", company_id=1)]
    mocker.patch("app.features.printers.printer_service.async_printer_repository.get_all", new_callable=AsyncMock,
                 return_value=mock_printers)

    result = await printer_service.get_all(async_db_mock, skip=0, limit=10)
    assert result == mock_printers


@pytest.mark.asyncio
async def test_printer_service_create(async_db_mock, mocker):
    printer_in = PrinterCreate(name="P1", address="192.168.1.10", company_id=1)
    mock_printer = Printer(id=1, name="P1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.async_printer_repository.create", new_callable=AsyncMock,
                 return_value=mock_printer)
    mocker.patch("app.features.printers.printer_service.audit_service.async_log_change", new_callable=AsyncMock)

    result = await printer_service.create(async_db_mock, printer_in, current_user_id=1)
    assert result == mock_printer


@pytest.mark.asyncio
async def test_printer_service_update(async_db_mock, mocker):
    printer_update = PrinterUpdate(name="Updated P1")
    mock_printer = Printer(id=1, name="Updated P1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.async_printer_repository.get_by_id", new_callable=AsyncMock,
                 return_value=mock_printer)
    mocker.patch("app.features.printers.printer_service.async_printer_repository.update", new_callable=AsyncMock,
                 return_value=mock_printer)
    mocker.patch("app.features.printers.printer_service.serialize_model", return_value={})
    mocker.patch("app.features.printers.printer_service.audit_service.async_log_change", new_callable=AsyncMock)

    result = await printer_service.update(async_db_mock, 1, printer_update, current_user_id=1)
    assert result == mock_printer


@pytest.mark.asyncio
async def test_printer_service_delete(async_db_mock, mocker):
    mock_printer = Printer(id=1, name="P1", address="192.168.1.10", company_id=1)
    mocker.patch("app.features.printers.printer_service.async_printer_repository.get_by_id", new_callable=AsyncMock,
                 return_value=mock_printer)
    mock_delete = mocker.patch("app.features.printers.printer_service.async_printer_repository.delete",
                               new_callable=AsyncMock)
    mocker.patch("app.features.printers.printer_service.audit_service.async_log_change", new_callable=AsyncMock)

    await printer_service.delete(async_db_mock, 1, current_user_id=1)
    mock_delete.assert_called_once_with(async_db_mock, printer_id=1)
