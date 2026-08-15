import io
from datetime import date
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.shared.enums import UserRole
from app.features.reports.report_schemas import (
    AdvancedUserReportResponse,
    DashboardMetricsResponse,
    HistoryResponse,
    MyDashboardResponse,
    TeamHoursResponse,
    UserPayrollSummary,
)
from app.features.users.user_models import User
from app.main import app


@pytest.fixture
def mock_manager_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MANAGER
    user.is_active = True
    user.can_export_report = True
    return user


@pytest.fixture
def client(mock_manager_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_dashboard(client: TestClient, mocker: MagicMock) -> None:
    expected = DashboardMetricsResponse(
        total_active_employees=9,
        pending_adjustments=2,
        employees_present_today=8,
        date=date(2026, 8, 14),
    )
    mocker.patch("app.features.reports.report_router.dashboard_service.get_dashboard_metrics", return_value=expected)

    response = client.get("/api/v1/reports/dashboard")
    assert response.status_code == 200
    assert response.json()["total_active_employees"] == 9


def test_get_my_dashboard(client: TestClient, mocker: MagicMock) -> None:
    expected = MyDashboardResponse(
        full_name="Manager",
        next_punch_type="ENTRY",
        today_punches=[],
        month_anomalies=[],
        aniversariantes_do_mes=[],
        server_time_unix=1234567890,
        server_time_formatted="14/08/2026 10:00",
    )
    mocker.patch("app.features.reports.report_router.dashboard_service.get_my_dashboard", return_value=expected)

    response = client.get("/api/v1/reports/my/dashboard")
    assert response.status_code == 200
    assert response.json()["full_name"] == "Manager"


def test_get_my_history(client: TestClient, mocker: MagicMock) -> None:
    expected = HistoryResponse(
        month=8,
        year=2026,
        total_worked_time="00:00",
        days=[],
    )
    mocker.patch("app.features.reports.report_router.report_service.get_history_report", return_value=expected)

    response = client.get("/api/v1/reports/history/me?month=8&year=2026")
    assert response.status_code == 200
    assert response.json()["month"] == 8


def test_get_user_history(client: TestClient, mocker: MagicMock) -> None:
    expected = HistoryResponse(
        month=8,
        year=2026,
        total_worked_time="00:00",
        days=[],
    )
    mocker.patch("app.features.reports.report_router.report_service.get_history_report", return_value=expected)

    response = client.get("/api/v1/reports/history/user/2?month=8&year=2026")
    assert response.status_code == 200
    assert response.json()["month"] == 8


def test_get_team_hours(client: TestClient, mocker: MagicMock) -> None:
    expected = TeamHoursResponse(
        month=8,
        year=2026,
        team_total_hours=160.0,
        team_formatted_time="160:00",
        employees=[],
    )
    mocker.patch("app.features.reports.report_router.dashboard_service.get_team_worked_hours", return_value=expected)

    response = client.get("/api/v1/reports/team-hours?month=8&year=2026")
    assert response.status_code == 200
    assert response.json()["team_total_hours"] == 160.0


def test_export_monthly_report_excel(client: TestClient, mocker: MagicMock) -> None:
    fake_stream = io.BytesIO(b"fake excel content")
    mocker.patch("app.features.reports.report_router.report_service.validate_excel_export_permission")
    mocker.patch("app.features.reports.report_router.excel_service.generate_excel_report", return_value=fake_stream)

    response = client.get("/api/v1/reports/export/excel?month=8&year=2026")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "folha_ponto_8_2026.xlsx" in response.headers["content-disposition"]


def test_get_user_detailed_report(client: TestClient, mocker: MagicMock) -> None:
    expected = AdvancedUserReportResponse(
        summary=UserPayrollSummary(
            user_id=1,
            user_name="Funcionario",
            total_worked_time="00:00",
            total_expected_time="00:00",
            days_worked=0,
            absences=0,
        ),
        daily_details=[],
    )
    mocker.patch("app.features.reports.report_router.report_service.get_advanced_user_report", return_value=expected)

    response = client.get("/api/v1/reports/user/1?month=8&year=2026")
    assert response.status_code == 200
    assert response.json()["summary"]["user_name"] == "Funcionario"
