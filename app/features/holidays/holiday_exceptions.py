from fastapi import status

from app.core.exceptions import DomainException


class HolidayAlreadyExistsError(DomainException):
    def __init__(self, date_str: str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Já existe um feriado cadastrado para a data {date_str}." if date_str else "Já existe um feriado cadastrado para esta data."
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
