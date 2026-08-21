from fastapi import status

from app.core.exceptions import DomainException


class DeviceCredentialNotFoundError(DomainException):
    def __init__(self, detail: str = "Credencial não encontrada."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class InvalidFirmwareVersionError(DomainException):
    def __init__(self, detail: str = "A versão deve estar no formato vx.x.x (ex: v0.3.1)"):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class InvalidFirmwareFileTypeError(DomainException):
    def __init__(self, detail: str = "Apenas arquivos .bin são permitidos"):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class FirmwareVersionNotGreaterError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class FirmwareVersionAlreadyExistsError(DomainException):
    def __init__(self, detail: str = "Versão já existe"):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class FirmwareNotFoundError(DomainException):
    def __init__(self, detail: str = "Firmware não encontrado"):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class NoFirmwareAvailableError(DomainException):
    def __init__(self, detail: str = "Nenhum firmware disponível"):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class FirmwareFileNotFoundError(DomainException):
    def __init__(self, detail: str = "Arquivo do firmware não encontrado no servidor"):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class SyncConsumerOnlyError(DomainException):
    def __init__(self, detail: str = "Apenas o Consumidor pode receber o banco de dados."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class SyncDatabaseCorruptedError(DomainException):
    def __init__(self, detail: str = "Arquivo de banco de dados corrompido ou invalido."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class SyncDatabaseReceiveError(DomainException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
