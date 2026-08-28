from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.features.printers.printer_exceptions import PrinterNotFoundError
from app.features.printers.printer_models import Printer
from app.features.printers.printer_repository import AsyncPrinterRepository, async_printer_repository
from app.features.printers.printer_schemas import PrinterCreate, PrinterUpdate
from app.features.system.audit_service import audit_service, serialize_model

PRINTER_NOT_FOUND_MSG = "Impressora não encontrada."


class PrinterService:
    def __init__(
        self,
            db: Annotated[AsyncSession, Depends(get_async_db)] = None,
            repo: Annotated[AsyncPrinterRepository, Depends()] = None,
    ):
        self.db = db
        self._repo = repo

    @property
    def repo(self) -> AsyncPrinterRepository:
        return self._repo if self._repo is not None else async_printer_repository

    @repo.setter
    def repo(self, value: AsyncPrinterRepository) -> None:
        self._repo = value

    async def get_by_id(self, db: AsyncSession | None = None, printer_id: int = 0) -> Printer:
        session = db if db is not None else self.db
        assert session is not None
        printer = await self.repo.get_by_id(session, printer_id=printer_id)
        if not printer:
            raise PrinterNotFoundError(printer_id=printer_id)
        return printer

    async def get_all(self, db: AsyncSession | None = None, skip: int = 0, limit: int = 100) -> list[Printer]:
        session = db if db is not None else self.db
        assert session is not None
        return await self.repo.get_all(session, skip=skip, limit=limit)

    async def create(self, db: AsyncSession | None = None, obj_in: PrinterCreate | None = None,
                     current_user_id: int = 0) -> Printer:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        printer = await self.repo.create(session, obj_in=obj_in)
        await audit_service.async_log_change(session, current_user_id, "CREATE", new_model=printer)
        return printer

    async def update(self, db: AsyncSession | None = None, printer_id: int = 0, obj_in: PrinterUpdate | None = None,
                     current_user_id: int = 0) -> Printer:
        session = db if db is not None else self.db
        assert session is not None
        assert obj_in is not None
        printer = await self.get_by_id(session, printer_id=printer_id)
        old_data = serialize_model(printer)
        updated_printer = await self.repo.update(session, db_obj=printer, obj_in=obj_in)
        await audit_service.async_log_change(session, current_user_id, "UPDATE", old_model=old_data,
                                             new_model=updated_printer)
        return updated_printer

    async def delete(self, db: AsyncSession | None = None, printer_id: int = 0, current_user_id: int = 0) -> None:
        session = db if db is not None else self.db
        assert session is not None
        printer = await self.get_by_id(session, printer_id=printer_id)
        await audit_service.async_log_change(session, current_user_id, "DELETE", old_model=printer)
        await self.repo.delete(session, printer_id=printer_id)


printer_service = PrinterService()
