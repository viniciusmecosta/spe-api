from fastapi import status

from app.core.exceptions import DomainException


class PrinterNotFoundError(DomainException):
    def __init__(self, detail: str = "Impressora não encontrada."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)
