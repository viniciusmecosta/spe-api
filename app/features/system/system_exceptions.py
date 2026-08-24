from fastapi import status

from app.core.exceptions import DomainException


class TelegramInvalidDateRangeError(DomainException):
    def __init__(self, detail: str = "A data de início não pode ser maior que a data de fim."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class TelegramPeriodExceededError(DomainException):
    def __init__(self,
                 detail: str = "Período excedido. O relatório gerencial no Telegram é limitado a no máximo 7 dias. Utilize a plataforma web para consultar períodos mais extensos."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class EmailNotConfiguredError(DomainException):
    def __init__(self, detail: str = "Serviço de email não configurado. Verifique as variáveis de ambiente (SMTP)."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class NoMaintainersWithEmailError(DomainException):
    def __init__(self, detail: str = "Nenhum mantenedor com e-mail cadastrado."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class BackupGenerationFailedError(DomainException):
    def __init__(self, detail: str = "Falha ao gerar a cópia de segurança do banco de dados local."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class SMTPConnectionFailedError(DomainException):
    def __init__(self, detail: str = "Falha na conexão SMTP ao tentar enviar o email."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
