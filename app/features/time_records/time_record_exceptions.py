from fastapi import status

from app.core.exceptions import DomainException


class TimeRecordUserNotFoundError(DomainException):
    def __init__(self, detail: str = "Usuário não encontrado."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ManualPunchUnauthorizedError(DomainException):
    def __init__(self, detail: str = "Registro manual não autorizado. Utilize a biometria."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class TimeRecordNotFoundError(DomainException):
    def __init__(self, detail: str = "Registro de ponto não encontrado."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class TimeRecordAccessDeniedError(DomainException):
    def __init__(self, detail: str = "Acesso negado."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class InvalidReceiptIdError(DomainException):
    def __init__(self, detail: str = "ID do comprovante inválido."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ReceiptAccessDeniedError(DomainException):
    def __init__(self, detail: str = "Acesso negado ao comprovante."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)
