from fastapi import status

from app.core.exceptions import DomainException


class CompanyAlreadyExistsError(DomainException):
    def __init__(self, detail: str = "Empresa já cadastrada. Utilize a atualização."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class CompanyNotFoundError(DomainException):
    def __init__(self, detail: str = "Nenhuma empresa cadastrada para atualizar."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class InvalidLogoFormatError(DomainException):
    def __init__(self, detail: str = "Formato de arquivo inválido. Apenas PNG, JPG ou JPEG são aceitos."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class LogoSaveError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
