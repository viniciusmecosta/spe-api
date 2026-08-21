from fastapi import status

from app.core.exceptions import DomainException


class WaiverLimitExceededError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AdjustmentNotFoundError(DomainException):
    def __init__(self, detail: str = "Solicitação não encontrada."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class InvalidAdjustmentTypeError(DomainException):
    def __init__(self, detail: str = "Apenas ajustes do tipo EXTRA_TIME e WAIVER podem ser excluídos."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AdjustmentPermissionError(DomainException):
    def __init__(self, detail: str = "Acesso negado.", status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(detail=detail, status_code=status_code)


class InvalidAdjustmentFilenameError(DomainException):
    def __init__(self, detail: str = "Nome de arquivo inválido."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class InvalidAttachmentFormatError(DomainException):
    def __init__(self, detail: str = "Formato inválido. Permitido apenas PDF, JPG ou PNG."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class CorruptedAttachmentError(DomainException):
    def __init__(self, detail: str = "O conteúdo do arquivo não corresponde à extensão ou está corrompido."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class WaiverAttachmentRequiredError(DomainException):
    def __init__(self, detail: str = "Para aprovar um abono, é obrigatório haver anexo."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AdjustmentInvalidStatusError(DomainException):
    def __init__(self, detail: str = "Apenas solicitações pendentes podem ser canceladas."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AdjustmentAttachmentNotFoundError(DomainException):
    def __init__(self, detail: str = "Nenhum anexo associado a este ajuste"):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class AttachmentFileNotFoundError(DomainException):
    def __init__(self, detail: str = "Arquivo físico não encontrado no servidor"):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)
