from fastapi import status

from app.core.exceptions import DomainException


class PayrollPermissionError(DomainException):
    def __init__(self, detail: str = "Acesso negado: Sem permissão para realizar operações na folha de pagamento."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class PayrollInvalidPeriodError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class PayrollAlreadyClosedError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class PayrollReportGenerationError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class PayrollNotClosedError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class PayrollPeriodClosedError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class PayrollClosureNotFoundError(DomainException):
    def __init__(self, period: str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Fechamento de folha para o período '{period}' não encontrado." if period else "Fechamento não encontrado."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)
