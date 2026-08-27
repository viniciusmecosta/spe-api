from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.features.printers.printer_exceptions import PrinterNotFoundError
from app.features.printers.printer_models import Printer
from app.features.printers.printer_repository import PrinterRepository, printer_repository
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate
from app.features.system.audit_service import audit_service, serialize_model
from app.shared import deps

PRINTER_NOT_FOUND_MSG = "Impressora não encontrada."


class PrinterService:
    def __init__(
        self,
        db: Annotated[Session, Depends(deps.get_db)] = None,
        repo: Annotated[PrinterRepository, Depends()] = None,
    ):
        self.db = db
        self.repo = repo if repo is not None else printer_repository

    def get_by_id(self, db: Session | None = None, printer_id: int = 0) -> Printer:
        session = db if db is not None else self.db
        assert session is not None
        printer = self.repo.get_by_id(session, printer_id=printer_id)
        if not printer:
            raise PrinterNotFoundError(printer_id=printer_id)
        return printer

    def get_all(self, db: Session | None = None, skip: int = 0, limit: int = 100) -> list[Printer]:
        session = db if db is not None else self.db
        assert session is not None
        return self.repo.get_all(session, skip=skip, limit=limit)

    def create(self, db: Session | None = None, obj_in: PrinterCreate | None = None, current_user_id: int = 0) -> Printer:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        printer = self.repo.create(session, obj_in=obj_in)
        audit_service.log_change(session, current_user_id, "CREATE", new_model=printer)
        return printer

    def update(self, db: Session | None = None, printer_id: int = 0, obj_in: PrinterUpdate | None = None, current_user_id: int = 0) -> Printer:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        printer = self.get_by_id(session, printer_id=printer_id)
        old_data = serialize_model(printer)
        updated_printer = self.repo.update(session, db_obj=printer, obj_in=obj_in)
        audit_service.log_change(session, current_user_id, "UPDATE", old_model=old_data, new_model=updated_printer)
        return updated_printer

    def delete(self, db: Session | None = None, printer_id: int = 0, current_user_id: int = 0) -> None:
        session = db if db is not None else self.db
        assert session is not None
        printer = self.get_by_id(session, printer_id=printer_id)
        audit_service.log_change(session, current_user_id, "DELETE", old_model=printer)
        self.repo.delete(session, printer_id=printer_id)


printer_service = PrinterService()
