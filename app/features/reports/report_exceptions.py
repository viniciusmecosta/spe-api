from fastapi import status

from app.core.exceptions import DomainException


class ReportUserNotFoundError(DomainException):
    def __init__(self, user_id: int | str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Usuário de ID {user_id} não encontrado para geração de relatório." if user_id is not None else "Usuário não encontrado."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ReportGlobalPermissionError(DomainException):
    def __init__(self, detail: str = "O usuário não possui privilégios suficientes para acessar relatórios globais."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class ReportAccessDeniedError(DomainException):
    def __init__(self, user_id: int | str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Acesso negado. Você não tem permissão para acessar o histórico do usuário (ID {user_id})." if user_id is not None else "Sem permissão para acessar o histórico deste usuário."
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class ReportNotFoundOrIncompleteError(DomainException):
    def __init__(self, user_id: int | str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Usuário (ID {user_id}) não encontrado ou com dados incompletos para o relatório." if user_id is not None else "Usuário não encontrado ou dados incompletos."
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
    def __init__(self, period: str | None = None, detail: str | None = None):
        if detail is None:
            detail = f"Período '{period}' não permitido. Funcionários só podem gerar relatório Excel do mês atual ou do mês anterior." if period else "Funcionários só podem gerar relatório Excel do mês atual ou do mês anterior."
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
