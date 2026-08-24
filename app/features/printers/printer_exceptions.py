from fastapi import status

from app.core.exceptions import DomainException


class PrinterNotFoundError(DomainException):
    def __init__(self, printer_id: int | str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Impressora de ID {printer_id} não encontrada." if printer_id is not None else "Impressora não encontrada."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)
