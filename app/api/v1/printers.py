from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_manager
from app.domain.models.user import User
from app.repositories.printer_repository import printer_repository
from app.schemas.printer import Printer, PrinterCreate, PrinterUpdate

router = APIRouter()


@router.get("/", response_model=List[Printer])
def read_printers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_manager),
):
    printers = printer_repository.get_all(db, skip=skip, limit=limit)
    return printers


@router.get("/{printer_id}", response_model=Printer)
def read_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_manager),
):
    printer = printer_repository.get_by_id(db, printer_id=printer_id)
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return printer


@router.post("/", response_model=Printer, status_code=status.HTTP_201_CREATED)
def create_printer(
    *,
    db: Session = Depends(get_db),
    printer_in: PrinterCreate,
    current_user: User = Depends(get_current_manager),
):
    return printer_repository.create(db, obj_in=printer_in)


@router.patch("/{printer_id}", response_model=Printer)
def update_printer(
    *,
    db: Session = Depends(get_db),
    printer_id: int,
    printer_in: PrinterUpdate,
    current_user: User = Depends(get_current_manager),
):
    printer = printer_repository.get_by_id(db, printer_id=printer_id)
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return printer_repository.update(db, db_obj=printer, obj_in=printer_in)


@router.delete("/{printer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_printer(
    *,
    db: Session = Depends(get_db),
    printer_id: int,
    current_user: User = Depends(get_current_manager),
):
    printer = printer_repository.get_by_id(db, printer_id=printer_id)
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    printer_repository.delete(db, db_obj=printer)
