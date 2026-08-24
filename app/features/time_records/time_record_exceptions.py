from fastapi import status

from app.core.exceptions import DomainException


class TimeRecordUserNotFoundError(DomainException):
    def __init__(self, user_id: int | str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Usuário de ID {user_id} não encontrado." if user_id is not None else "Usuário não encontrado."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ManualPunchUnauthorizedError(DomainException):
    def __init__(self, detail: str = "Registro manual não autorizado. Utilize a biometria."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class TimeRecordNotFoundError(DomainException):
    def __init__(self, record_id: int | str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Registro de ponto (ID {record_id}) não encontrado." if record_id is not None else "Registro de ponto não encontrado."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class TimeRecordAccessDeniedError(DomainException):
    def __init__(self, detail: str = "Acesso negado. Você não possui privilégios de gestor para visualizar ou editar os registros deste usuário.", status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(detail=detail, status_code=status_code)


class InvalidReceiptIdError(DomainException):
    def __init__(self, receipt_id: str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"O ID de comprovante '{receipt_id}' fornecido é inválido." if receipt_id else "ID do comprovante inválido."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ReceiptAccessDeniedError(DomainException):
    def __init__(self, detail: str = "Acesso negado. Você não tem permissão para visualizar este comprovante de ponto.", status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(detail=detail, status_code=status_code)
