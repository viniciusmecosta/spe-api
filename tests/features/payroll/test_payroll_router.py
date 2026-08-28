import io
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.payroll.payroll_schemas import PayrollClosureResponse
from app.features.payroll.payroll_service import PayrollService
from app.features.time_records.time_record_schemas import SuccessResponse
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def mock_maintainer_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MAINTAINER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_maintainer_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_list_payroll_periods(client: TestClient, mocker: MagicMock) -> None:
    expected = [
        PayrollClosureResponse(
            id=1,
            month=8,
            year=2026,
            closed_at=datetime(2026, 8, 14, 10, 0, 0),
            closed_by_user_id=1,
            closed_by_user_name="Maintainer",
            is_closed=True,
        )
    ]
    mocker.patch.object(
        PayrollService,
        "list_periods",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.get("/api/v1/payroll/?year=2026")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["month"] == 8


def test_close_payroll_period(client: TestClient, mocker: MagicMock) -> None:
    expected = PayrollClosureResponse(
        id=1,
        month=8,
        year=2026,
        closed_at=datetime(2026, 8, 14, 10, 0, 0),
        closed_by_user_id=1,
        closed_by_user_name="Maintainer",
        is_closed=True,
    )
    mocker.patch.object(
        PayrollService,
        "close_period",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.post("/api/v1/payroll/close", json={"month": 8, "year": 2026})
    assert response.status_code == 200
    assert response.json()["is_closed"] is True


def test_reopen_payroll_period(client: TestClient, mocker: MagicMock) -> None:
    expected = SuccessResponse(status="success", message="Period reopened")
    mocker.patch.object(
        PayrollService,
        "reopen_period",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.post(
        "/api/v1/payroll/reopen",
        json={"month": 8, "year": 2026, "observation": "Reopen for adjustment"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_upload_legacy_report(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(PayrollService, "upload_legacy_report", new_callable=AsyncMock)

    test_file = io.BytesIO(b"fake pdf legacy report")
    response = client.post(
        "/api/v1/payroll/1/legacy-report",
        files={"file": ("legacy.pdf", test_file, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
