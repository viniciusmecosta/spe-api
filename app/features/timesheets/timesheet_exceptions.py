from fastapi import status

from app.core.exceptions import DomainException


class InvalidMonthOrYearError(DomainException):
    def __init__(self, detail: str = "Mês ou ano inválido."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class FutureTimesheetNotAllowedError(DomainException):
    def __init__(self, detail: str = "Não é possível solicitar espelhos de ponto referentes a meses futuros."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class TimesheetUserNotFoundError(DomainException):
    def __init__(self, detail: str = "Usuário não encontrado."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class NoTimesheetRecordsFoundError(DomainException):
    def __init__(self, detail: str = "Nenhum registro de ponto encontrado para gerar os espelhos neste mês."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)
