from typing import List

from sqlalchemy.orm import Session

from app.domain.models.printer import Printer
from app.schemas.printer import PrinterCreate, PrinterUpdate


class PrinterRepository:
    def get_by_id(self, db: Session, printer_id: int) -> Printer | None:
        return db.query(Printer).filter(Printer.id == printer_id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[Printer]:
        return db.query(Printer).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: PrinterCreate) -> Printer:
        db_obj = Printer(
            name=obj_in.name,
            address=obj_in.address,
            status=obj_in.status,
            paper_width=obj_in.paper_width,
            company_id=obj_in.company_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: Printer, obj_in: PrinterUpdate) -> Printer:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, db_obj: Printer) -> Printer:
        db.delete(db_obj)
        db.commit()
        return db_obj


printer_repository = PrinterRepository()
