from datetime import date, datetime
from unittest.mock import MagicMock, patch, mock_open
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, HTTPException, status

import pytest
from app.shared.enums import UserRole
from app.features.payroll.payroll_models import PayrollClosure
from app.features.payroll.payroll_service import payroll_service
from app.features.users.user_models import User


@pytest.fixture
def mock_background_tasks():
    return MagicMock(spec=BackgroundTasks)


@pytest.fixture
def mock_user_manager():
    user = MagicMock(spec=User)
    user.id = 1
    user.name = "Manager"
    user.role = UserRole.MANAGER
    return user


@pytest.fixture
def mock_user_maintainer():
    user = MagicMock(spec=User)
    user.id = 2
    user.name = "Maintainer"
    user.role = UserRole.MAINTAINER
    return user


@pytest.fixture
def mock_user_employee():
    user = MagicMock(spec=User)
    user.id = 3
    user.name = "Employee"
    user.role = UserRole.EMPLOYEE
    return user


def test_build_history():
    closure1 = MagicMock()
    closure1.closed_at = datetime(2023, 1, 10)
    closure1.closed_by_user_id = 1
    closure1.closed_by.name = "Manager"
    closure1.deleted_at = None
    
    closure2 = MagicMock()
    closure2.closed_at = datetime(2023, 1, 5)
    closure2.closed_by_user_id = 2
    closure2.closed_by.name = "Maintainer"
    closure2.deleted_at = datetime(2023, 1, 8)
    closure2.deleted_by = 2
    closure2.deleter.name = "Maintainer"
    closure2.reopen_observation = "Mistake"
    
    closures = [closure1, closure2]
    history = payroll_service._build_history(closures)
    
    assert len(history) == 3
    assert history[0]["action"] == "Fechamento"
    assert history[0]["timestamp"] == datetime(2023, 1, 10)
    
    assert history[1]["action"] == "Reabertura"
    assert history[1]["timestamp"] == datetime(2023, 1, 8)
    
    assert history[2]["action"] == "Fechamento"
    assert history[2]["timestamp"] == datetime(2023, 1, 5)


def test_build_history_no_names():
    closure1 = MagicMock()
    closure1.closed_at = datetime(2023, 1, 10)
    closure1.closed_by_user_id = 1
    closure1.closed_by = None
    closure1.deleted_at = datetime(2023, 1, 12)
    closure1.deleted_by = 1
    closure1.deleter = None
    closure1.reopen_observation = "Test"
    
    closures = [closure1]
    history = payroll_service._build_history(closures)
    
    assert len(history) == 2
    assert history[0]["user_name"] is None
    assert history[1]["user_name"] is None


def test_build_period_response_no_closure():
    response = payroll_service._build_period_response(1, 2023, {})
    assert response["month"] == 1
    assert response["year"] == 2023
    assert response["is_closed"] is False
    assert response["id"] is None
    assert response["closed_at"] is None
    assert response["closed_by_user_id"] is None
    assert response["closed_by_name"] is None
    assert response["history"] == []


def test_build_period_response_with_closure():
    closure = MagicMock()
    closure.id = 10
    closure.closed_at = datetime(2023, 1, 10)
    closure.closed_by_user_id = 1
    closure.closed_by.name = "Manager"
    closure.deleted_at = None
    
    closures_by_month = {1: [closure]}
    response = payroll_service._build_period_response(1, 2023, closures_by_month)
    
    assert response["month"] == 1
    assert response["year"] == 2023
    assert response["is_closed"] is True
    assert response["id"] == 10
    assert response["closed_at"] == datetime(2023, 1, 10)
    assert response["closed_by_user_id"] == 1
    assert response["closed_by_name"] == "Manager"
    assert len(response["history"]) == 1


def test_build_period_response_with_closure_no_name():
    closure = MagicMock()
    closure.id = 10
    closure.closed_at = datetime(2023, 1, 10)
    closure.closed_by_user_id = 1
    closure.closed_by = None
    closure.deleted_at = None
    
    closures_by_month = {1: [closure]}
    response = payroll_service._build_period_response(1, 2023, closures_by_month)
    
    assert response["closed_by_name"] is None


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
def test_list_periods_past_year(mock_datetime, db_session_mock):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    db_session_mock.query.return_value.items = []
    
    result = payroll_service.list_periods(db_session_mock, 2023)
    assert len(result) == 12
    assert result[0]["month"] == 12
    assert result[-1]["month"] == 1


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
def test_list_periods_current_year(mock_datetime, db_session_mock):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    closure = MagicMock(spec=PayrollClosure)
    closure.month = 2
    closure.year = 2024
    closure.id = 1
    closure.deleted_at = None
    closure.closed_by = None
    db_session_mock.query.return_value.items = [closure]
    
    result = payroll_service.list_periods(db_session_mock, 2024)
    assert len(result) == 5
    assert result[0]["month"] == 5
    assert result[-1]["month"] == 1
    assert result[3]["is_closed"] is True
    assert result[3]["month"] == 2


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
def test_list_periods_future_year(mock_datetime, db_session_mock):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    db_session_mock.query.return_value.items = []
    
    result = payroll_service.list_periods(db_session_mock, 2025)
    assert len(result) == 0


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
def test_list_periods_multiple_closures(mock_datetime, db_session_mock):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    closure1 = MagicMock(spec=PayrollClosure)
    closure1.month = 2
    closure1.year = 2024
    closure1.id = 1
    closure1.closed_at = datetime(2024, 2, 28)
    closure1.deleted_at = datetime(2024, 3, 1)
    closure1.closed_by = None
    closure1.deleter = None
    closure2 = MagicMock(spec=PayrollClosure)
    closure2.month = 2
    closure2.year = 2024
    closure2.id = 2
    closure2.closed_at = datetime(2024, 3, 2)
    closure2.deleted_at = None
    closure2.closed_by = None
    
    db_session_mock.query.return_value.items = [closure1, closure2]
    
    result = payroll_service.list_periods(db_session_mock, 2024)
    assert len(result) == 5
    month_2 = next(r for r in result if r["month"] == 2)
    assert month_2["is_closed"] is True
    assert month_2["id"] == 2
    assert len(month_2["history"]) == 3


def test_close_period_forbidden(db_session_mock, mock_user_employee, mock_background_tasks):
    with pytest.raises(HTTPException) as exc:
        payroll_service.close_period(db_session_mock, 1, 2024, mock_user_employee, mock_background_tasks)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
def test_close_period_current_month(mock_datetime, db_session_mock, mock_user_manager, mock_background_tasks):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    with pytest.raises(HTTPException) as exc:
        payroll_service.close_period(db_session_mock, 5, 2024, mock_user_manager, mock_background_tasks)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
def test_close_period_future_month(mock_datetime, db_session_mock, mock_user_manager, mock_background_tasks):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    with pytest.raises(HTTPException) as exc:
        payroll_service.close_period(db_session_mock, 6, 2024, mock_user_manager, mock_background_tasks)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
@patch("app.features.payroll.payroll_service.payroll_repository")
def test_close_period_already_closed(mock_repo, mock_datetime, db_session_mock, mock_user_manager, mock_background_tasks):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    mock_repo.get_by_month.return_value = MagicMock()
    
    with pytest.raises(HTTPException) as exc:
        payroll_service.close_period(db_session_mock, 4, 2024, mock_user_manager, mock_background_tasks)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


@patch("app.features.payroll.payroll_service.settings.TIMEZONE", "UTC")
@patch("app.features.payroll.payroll_service.datetime")
@patch("app.features.payroll.payroll_service.dispatch_closure_email_background")
@patch("app.features.payroll.payroll_service.audit_service")
@patch("app.features.payroll.payroll_service.payroll_repository")
@patch("app.features.payroll.payroll_service.excel_service")
def test_close_period_success(mock_excel, mock_repo, mock_audit, mock_dispatch, mock_datetime, db_session_mock, mock_user_manager, mock_background_tasks):
    mock_now = datetime(2024, 5, 15, tzinfo=ZoneInfo("UTC"))
    mock_datetime.now.return_value = mock_now
    
    mock_repo.get_by_month.return_value = None
    mock_closure = MagicMock(id=99)
    mock_repo.create.return_value = mock_closure
    
    from io import BytesIO
    mock_excel.generate_excel_report.return_value = BytesIO(b"data")

    maintainer = MagicMock(spec=User)
    maintainer.email = "main@test.com"
    db_session_mock.query.return_value.items = [maintainer]

    with patch("os.makedirs"), patch("builtins.open", new_callable=MagicMock()):
        result = payroll_service.close_period(db_session_mock, 4, 2024, mock_user_manager, mock_background_tasks)
    
    assert result == mock_closure
    mock_repo.create.assert_called_once_with(db_session_mock, 4, 2024, mock_user_manager.id)
    assert db_session_mock.commit.call_count == 2
    mock_audit.log_change.assert_called_once_with(
        db_session_mock, mock_user_manager.id, "CLOSE", new_model=mock_closure
    )
    mock_background_tasks.add_task.assert_called_once_with(
        mock_dispatch, 4, 2024, mock_user_manager.name, mock_closure.report_path, ["main@test.com"]
    )


def test_reopen_period_forbidden(db_session_mock, mock_user_manager, mock_background_tasks):
    with pytest.raises(HTTPException) as exc:
        payroll_service.reopen_period(db_session_mock, 4, 2024, "Obs", mock_user_manager, mock_background_tasks)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@patch("app.features.payroll.payroll_service.payroll_repository")
def test_reopen_period_not_found(mock_repo, db_session_mock, mock_user_maintainer, mock_background_tasks):
    mock_repo.get_by_month.return_value = None
    
    with pytest.raises(HTTPException) as exc:
        payroll_service.reopen_period(db_session_mock, 4, 2024, "Obs", mock_user_maintainer, mock_background_tasks)
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


@patch("app.features.payroll.payroll_service.dispatch_payroll_email")
@patch("app.features.payroll.payroll_service.audit_service")
@patch("app.features.payroll.payroll_service.payroll_repository")
def test_reopen_period_success(mock_repo, mock_audit, mock_dispatch, db_session_mock, mock_user_maintainer, mock_background_tasks):
    mock_closure = MagicMock(id=99)
    mock_repo.get_by_month.return_value = mock_closure
    
    maintainer = MagicMock(spec=User)
    maintainer.email = "main@test.com"
    db_session_mock.query.return_value.items = [maintainer]

    result = payroll_service.reopen_period(db_session_mock, 4, 2024, "Obs", mock_user_maintainer, mock_background_tasks)
    
    assert result["status"] == "success"
    mock_repo.delete.assert_called_once_with(db_session_mock, 4, 2024, mock_user_maintainer.id, "Obs")
    mock_audit.log_change.assert_called_once_with(
        db_session_mock, mock_user_maintainer.id, "REOPEN", old_model=mock_closure
    )
    mock_background_tasks.add_task.assert_called_once_with(
        mock_dispatch, "Reabertura", mock_user_maintainer.name, 4, 2024, ["main@test.com"]
    )


def test_upload_legacy_report_success(db_session_mock, mock_user_maintainer):
    mock_closure = MagicMock(id=1, month=4, year=2024)
    db_session_mock.query.return_value.get = MagicMock(return_value=mock_closure)
    
    with patch("os.makedirs"), patch("builtins.open", new_callable=MagicMock()):
        payroll_service.upload_legacy_report(db_session_mock, 1, "test.pdf", b"data")
    
    db_session_mock.commit.assert_called_once()
    assert mock_closure.report_path.startswith("reports/legacy/folha_ponto_04_2024_")
    assert mock_closure.report_path.endswith(".pdf")


def test_upload_legacy_report_not_found(db_session_mock, mock_user_maintainer):
    db_session_mock.query.return_value.get = MagicMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        payroll_service.upload_legacy_report(db_session_mock, 1, "test.pdf", b"data")
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


@patch("app.features.payroll.payroll_service.payroll_repository")
def test_validate_period_open_closed(mock_repo, db_session_mock):
    mock_repo.get_by_month.return_value = MagicMock()
    target_date = date(2024, 4, 15)
    with pytest.raises(HTTPException) as exc:
        payroll_service.validate_period_open(db_session_mock, target_date)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


@patch("app.features.payroll.payroll_service.payroll_repository")
def test_validate_period_open_success(mock_repo, db_session_mock):
    mock_repo.get_by_month.return_value = None
    
    payroll_service.validate_period_open(db_session_mock, date(2024, 4, 15))


@patch("app.features.payroll.payroll_service.email_service.send_payroll_email")
@patch("os.path.exists", return_value=True)
def test_dispatch_closure_email_background_with_attachment(mock_exists, mock_send):
    from app.features.payroll.payroll_service import dispatch_closure_email_background
    with patch("builtins.open", mock_open(read_data=b"dummycontent")):
        dispatch_closure_email_background(4, 2024, "User", "reports/file.xlsx", ["admin@test.com"])
    mock_send.assert_called_once()


@patch("app.features.payroll.payroll_service.email_service.send_payroll_email")
@patch("os.path.exists", return_value=False)
def test_dispatch_closure_email_background_no_attachment(mock_exists, mock_send):
    from app.features.payroll.payroll_service import dispatch_closure_email_background
    dispatch_closure_email_background(4, 2024, "User", "reports/file.xlsx", ["admin@test.com"])
    mock_send.assert_called_once()


@patch("app.features.payroll.payroll_service.email_service.send_payroll_email", side_effect=Exception("Email error"))
@patch("app.features.payroll.payroll_service.logger.exception")
def test_dispatch_closure_email_background_error(mock_log, mock_send):
    from app.features.payroll.payroll_service import dispatch_closure_email_background
    dispatch_closure_email_background(4, 2024, "User", "reports/file.xlsx", ["admin@test.com"])
    mock_log.assert_called_once()


@patch("app.features.payroll.payroll_service.excel_service.generate_excel_report",
       side_effect=Exception("Excel generation error"))
@patch("app.features.payroll.payroll_service.payroll_repository")
def test_close_period_excel_error(mock_repo, mock_gen, db_session_mock, mock_user_manager, mock_background_tasks):
    mock_repo.get_by_month.return_value = None
    with pytest.raises(HTTPException) as exc:
        payroll_service.close_period(db_session_mock, 4, 2024, mock_user_manager, mock_background_tasks)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Excel generation error" in exc.value.detail
