from fastapi import status

from app.core.exceptions import DomainException


class UserNotFoundError(DomainException):
    def __init__(self, detail: str = "Usuário não encontrado."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class UserAlreadyExistsError(DomainException):
    def __init__(self, detail: str = "Nome de usuário já em uso."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class InsufficientPrivilegesError(DomainException):
    def __init__(self, detail: str = "Privilégios insuficientes.", status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(detail=detail, status_code=status_code)


class BiometricValidationError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class SchedulePayrollClosedError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class ScheduleOverlapError(DomainException):
    def __init__(self, detail: str = "Já existe um expediente neste dia. Edite-o em vez de criar um novo."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class BulkScheduleNotFoundError(DomainException):
    def __init__(self, detail: str = "Expediente em massa não encontrado para esse período."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class BulkScheduleValidationError(DomainException):
    def __init__(self, detail: str | list):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
