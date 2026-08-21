from fastapi import status

from app.core.exceptions import DomainException


class HolidayAlreadyExistsError(DomainException):
    def __init__(self, detail: str = "Já existe um feriado cadastrado para esta data."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
