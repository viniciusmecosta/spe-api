from unittest.mock import MagicMock

import pytest
from app.features.printers.printer_models import Printer
from app.features.printers.printer_repository import AsyncPrinterRepository, PrinterRepository
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate


def test_printer_repository(db_session, company):
    repo = PrinterRepository()

    created = repo.create(
        db_session,
        obj_in=PrinterCreate(name="Repo Printer", address="192.168.1.100", status=True, paper_width=80,
                             company_id=company.id)
    )
    assert created.id is not None

    by_id = repo.get_by_id(db_session, created.id)
    assert by_id is not None

    all_p = repo.get_all(db_session)
    assert len(all_p) >= 1

    updated = repo.update(db_session, db_obj=created, obj_in=PrinterUpdate(name="Repo Printer Updated"))
    assert updated.name == "Repo Printer Updated"

    updated_dict = repo.update(db_session, db_obj=created, obj_in={"name": "Repo Printer Dict"})
    assert updated_dict.name == "Repo Printer Dict"

    deleted = repo.delete(db_session, created.id)
    assert deleted is True
    assert repo.delete(db_session, 99999) is False


@pytest.mark.asyncio
async def test_async_printer_repository(async_db_mock):
    repo = AsyncPrinterRepository()
    mock_printer = Printer(id=1, name="Async Printer", address="192.168.1.100", status=True, paper_width=80,
                           company_id=1)

    async_db_mock.get.return_value = mock_printer
    by_id = await repo.get_by_id(async_db_mock, 1)
    assert by_id == mock_printer

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_printer]
    async_db_mock.scalars.return_value = mock_scalars

    all_p = await repo.get_all(async_db_mock)
    assert len(all_p) == 1

    created = await repo.create(
        async_db_mock,
        obj_in=PrinterCreate(name="Async Printer", address="192.168.1.100", status=True, paper_width=80, company_id=1)
    )
    assert created.name == "Async Printer"

    updated = await repo.update(async_db_mock, db_obj=created, obj_in=PrinterUpdate(name="Updated"))
    assert updated.name == "Updated"

    deleted = await repo.delete(async_db_mock, 1)
    assert deleted is True
