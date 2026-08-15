import io
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pytest
from app.shared import deps
from app.domain.enums import UserRole
from app.features.users.user_models import User
from app.main import app


@pytest.fixture
def mock_manager_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MANAGER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_manager_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_manager] = lambda: mock_manager_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_official_timesheet_user_pdf_success(client: TestClient, mocker: MagicMock) -> None:
    fake_buffer = io.BytesIO(b"%PDF-1.4 fake pdf")
    mocker.patch(
        "app.features.timesheets.timesheet_router.timesheet_service.generate_user_timesheet_pdf",
        return_value=fake_buffer,
    )

    response = client.get("/api/v1/timesheets/user/1/pdf?month=1&year=2024")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=espelho_ponto_1_01_2024.pdf" in response.headers["content-disposition"]


def test_get_official_timesheet_user_pdf_future_date(client: TestClient) -> None:
    response = client.get("/api/v1/timesheets/user/1/pdf?month=12&year=2099")
    assert response.status_code == 400
    assert "meses futuros" in response.json()["detail"]


def test_get_official_timesheet_all_pdf_success(client: TestClient, mocker: MagicMock) -> None:
    fake_zip = io.BytesIO(b"PK fake zip")
    mocker.patch(
        "app.features.timesheets.timesheet_router.timesheet_service.generate_all_timesheets_pdf_zip",
        return_value=fake_zip,
    )

    response = client.get("/api/v1/timesheets/all/pdf?month=1&year=2024")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "espelhos_ponto_lote_01_2024.zip" in response.headers["content-disposition"]
