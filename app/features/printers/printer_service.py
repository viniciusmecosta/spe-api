from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.features.printers.printer_models import Printer
from app.features.printers.printer_repository import printer_repository
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate

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

    def create(self, db: Session, obj_in: PrinterCreate) -> Printer:
        return printer_repository.create(db, obj_in=obj_in)

    def update(self, db: Session, printer_id: int, obj_in: PrinterUpdate) -> Printer:
        printer = self.get_by_id(db, printer_id)
        return printer_repository.update(db, db_obj=printer, obj_in=obj_in)

    def delete(self, db: Session, printer_id: int) -> None:
        printer = self.get_by_id(db, printer_id)
        printer_repository.delete(db, db_obj=printer)


printer_service = PrinterService()
