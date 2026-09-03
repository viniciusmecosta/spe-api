from app.features.reports.report_exceptions import (
    ReportUserNotFoundError,
    ReportGlobalPermissionError,
    ReportAccessDeniedError,
    ReportNotFoundOrIncompleteError,
    PendingAdjustmentsExistError,
    ReportExportPermissionError,
    EmployeePreviousMonthOnlyError,
    PayrollNotClosedForReportError,
    EmployeeInvalidReportPeriodError,
)


def test_all_report_exceptions():
    e1 = ReportUserNotFoundError(1)
    assert "1" in e1.detail
    e1_none = ReportUserNotFoundError()
    assert e1_none.detail == "Usuário não encontrado."

    e2 = ReportGlobalPermissionError()
    assert "privilégios" in e2.detail

    e3 = ReportAccessDeniedError(1)
    assert "1" in e3.detail
    e3_none = ReportAccessDeniedError()
    assert "Sem permissão" in e3_none.detail

    e4 = ReportNotFoundOrIncompleteError(1)
    assert "1" in e4.detail
    e4_none = ReportNotFoundOrIncompleteError()
    assert "incompletos" in e4_none.detail

    e5 = PendingAdjustmentsExistError()
    assert "pendentes" in e5.detail

    e6 = ReportExportPermissionError()
    assert "permissão" in e6.detail

    e7 = EmployeePreviousMonthOnlyError()
    assert "anterior" in e7.detail

    e8 = PayrollNotClosedForReportError()
    assert "fechada" in e8.detail

    e9 = EmployeeInvalidReportPeriodError("2026-01")
    assert "2026-01" in e9.detail
    e9_none = EmployeeInvalidReportPeriodError()
    assert "anterior" in e9_none.detail
