from app.features.printers.printer_repository import PrinterRepository
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate


def test_printer_repository(db_session, company):
    repo = PrinterRepository()

    created = repo.create(
        db_session,
        PrinterCreate(name="Repo Printer", address="192.168.1.100", status=True, paper_width=80, company_id=company.id)
    )
    assert created.id is not None

    by_id = repo.get_by_id(db_session, created.id)
    assert by_id is not None

    all_p = repo.get_all(db_session)
    assert len(all_p) >= 1

    updated = repo.update(db_session, created, PrinterUpdate(name="Repo Printer Updated"))
    assert updated.name == "Repo Printer Updated"

    updated_dict = repo.update(db_session, created, {"name": "Repo Printer Dict"})
    assert updated_dict.name == "Repo Printer Dict"

    deleted = repo.delete(db_session, created.id)
    assert deleted is True
    assert repo.delete(db_session, 99999) is False
