from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.features.printers.printer_models import Printer
from app.features.printers.printer_repository import printer_repository
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate
from app.features.system.audit_service import audit_service, serialize_model

PRINTER_NOT_FOUND_MSG = "Printer not found"


class PrinterService:
    def get_by_id(self, db: Session, printer_id: int) -> Printer:
        printer = printer_repository.get_by_id(db, printer_id=printer_id)
        if not printer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=PRINTER_NOT_FOUND_MSG,
            )
        return printer

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> list[Printer]:
        return printer_repository.get_all(db, skip=skip, limit=limit)

    def create(self, db: Session, obj_in: PrinterCreate, current_user_id: int) -> Printer:
        printer = printer_repository.create(db, obj_in=obj_in)
        audit_service.log_change(db, current_user_id, "CREATE", new_model=printer)
        return printer

    def update(self, db: Session, printer_id: int, obj_in: PrinterUpdate, current_user_id: int) -> Printer:
        printer = self.get_by_id(db, printer_id)
        old_data = serialize_model(printer)
        updated_printer = printer_repository.update(db, db_obj=printer, obj_in=obj_in)
        audit_service.log_change(db, current_user_id, "UPDATE", old_model=old_data, new_model=updated_printer)
        return updated_printer

    def delete(self, db: Session, printer_id: int, current_user_id: int) -> None:
        printer = self.get_by_id(db, printer_id)
        audit_service.log_change(db, current_user_id, "DELETE", old_model=printer)
        printer_repository.delete(db, printer_id=printer_id)


printer_service = PrinterService()
