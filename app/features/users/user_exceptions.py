from typing import Any

from fastapi import status

from app.core.exceptions import DomainException


class UserNotFoundError(DomainException):
    def __init__(self, user_id: int | str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Usuário de ID {user_id} não encontrado." if user_id is not None else "Usuário não encontrado."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class UserAlreadyExistsError(DomainException):
    def __init__(self, detail: str = "Nome de usuário já em uso."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class InsufficientPrivilegesError(DomainException):
    def __init__(self, detail: str = "Privilégios insuficientes para realizar esta operação no usuário.", status_code: int = status.HTTP_403_FORBIDDEN):
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
    def __init__(self, valid_from: Any = None, valid_until: Any = None, detail: str | None = None):
        if detail is None:
            if valid_from is not None and valid_until is not None:
                detail = f"Expediente em massa não encontrado para o período de {valid_from} a {valid_until}."
            else:
                detail = "Expediente em massa não encontrado para esse período."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class BulkScheduleValidationError(DomainException):
    def __init__(self, detail: str | list):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
