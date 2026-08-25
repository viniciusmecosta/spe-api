from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.repository import BaseRepository
from app.features.printers.printer_models import Printer
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate


class PrinterRepository(BaseRepository[Printer, PrinterCreate, PrinterUpdate]):
    def __init__(self):
        super().__init__(Printer)

    def get_by_id(self, db: Session, printer_id: int) -> Printer | None:
        return super().get(db, printer_id)

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> list[Printer]:
        stmt = select(Printer).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    def create(self, db: Session, obj_in: PrinterCreate) -> Printer:
        return super().create(db, obj_in=obj_in)

    def update(self, db: Session, db_obj: Printer, obj_in: PrinterUpdate | dict[str, Any]) -> Printer:
        return super().update(db, db_obj=db_obj, obj_in=obj_in)

    def delete(self, db: Session, printer_id: int) -> bool:
        obj = super().remove(db, id=printer_id)
        return obj is not None


printer_repository = PrinterRepository()
