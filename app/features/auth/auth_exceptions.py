from fastapi import status

from app.core.exceptions import DomainException


class InvalidCredentialsError(DomainException):
    def __init__(self, detail: str = "Usuário ou senha incorretos."):
        super().__init__(detail=detail, status_code=status.HTTP_401_UNAUTHORIZED)


class InactiveUserError(DomainException):
    def __init__(self, detail: str = "Usuário inativo."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
