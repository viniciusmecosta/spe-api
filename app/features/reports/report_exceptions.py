from fastapi import status

from app.core.exceptions import DomainException


class ReportUserNotFoundError(DomainException):
    def __init__(self, detail: str = "Usuário não encontrado."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ReportGlobalPermissionError(DomainException):
    def __init__(self, detail: str = "O usuário não possui privilégios suficientes para acessar relatórios globais."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class ReportAccessDeniedError(DomainException):
    def __init__(self, detail: str = "Sem permissão para acessar o histórico deste usuário."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class ReportNotFoundOrIncompleteError(DomainException):
    def __init__(self, detail: str = "Usuário não encontrado ou dados incompletos."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class PendingAdjustmentsExistError(DomainException):
    def __init__(self, detail: str = "Não é possível gerar o relatório pois existem ajustes pendentes neste mês."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class ReportExportPermissionError(DomainException):
    def __init__(self, detail: str = "Você não tem permissão para gerar relatórios."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class EmployeePreviousMonthOnlyError(DomainException):
    def __init__(self, detail: str = "Funcionários só podem gerar o relatório referente ao mês anterior."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class PayrollNotClosedForReportError(DomainException):
    def __init__(self, detail: str = "Não é possível gerar o relatório pois a folha deste mês ainda não está fechada."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class EmployeeInvalidReportPeriodError(DomainException):
    def __init__(self, detail: str = "Funcionários só podem gerar relatório Excel do mês atual ou do mês anterior."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
