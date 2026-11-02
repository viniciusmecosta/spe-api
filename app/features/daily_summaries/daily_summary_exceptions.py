from fastapi import status

from app.core.exceptions import DomainException


class DailySummaryUnavailableError(DomainException):
    def __init__(self):
        super().__init__(
            "Apuração diária indisponível. Tente consultar novamente em instantes.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
