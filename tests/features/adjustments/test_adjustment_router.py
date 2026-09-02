import io
import os
import tempfile
from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pytest
from app.features.adjustments.adjustment_schemas import (
    AdjustmentAttachmentResponse,
    AdjustmentRequestResponse,
)
from app.features.adjustments.adjustment_service import AdjustmentService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType, UserRole


@pytest.fixture
def mock_maintainer_user() -> User:
    user = MagicMock(spec=User)
    user.id = 1
    user.role = UserRole.MAINTAINER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_maintainer_user: User, db_session_mock: MagicMock) -> TestClient:
    app.dependency_overrides[deps.get_current_active_user] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_current_manager] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_current_maintainer] = lambda: mock_maintainer_user
    app.dependency_overrides[deps.get_db] = lambda: db_session_mock
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_create_adjustment_request(client: TestClient, mocker: MagicMock) -> None:
    expected = AdjustmentRequestResponse(
        id=1,
        user_id=1,
        user_name="User Test",
        target_date=date(2026, 8, 14),
        adjustment_type=AdjustmentType.FORGOT_PUNCH,
        record_type=RecordType.ENTRY,
        time=time(8, 0),
        status=AdjustmentStatus.PENDING,
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        AdjustmentService,
        "create_adjustment_request",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.post(
        "/api/v1/adjustments/",
        json={
            "target_date": "2026-08-14",
            "adjustment_type": "FORGOT_PUNCH",
            "record_type": "ENTRY",
            "time": "08:00:00",
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] == 1


def test_waive_absence_admin(client: TestClient, mocker: MagicMock) -> None:
    expected = AdjustmentRequestResponse(
        id=2,
        user_id=1,
        user_name="User Test",
        target_date=date(2026, 8, 14),
        adjustment_type=AdjustmentType.WAIVER,
        amount_hours=2.0,
        reason_text="Abono chefia",
        status=AdjustmentStatus.APPROVED,
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        AdjustmentService,
        "create_manager_waiver",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.post(
        "/api/v1/adjustments/admin/waive",
        json={
            "user_id": 1,
            "target_date": "2026-08-14",
            "amount_hours": 2.0,
            "reason_text": "Abono chefia",
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] == 2


def test_reprocess_historical_daily_excess(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(
        AdjustmentService,
        "reprocess_historical_daily_excess",
        new_callable=AsyncMock,
        return_value={"status": "success", "message": "Reprocessamento de excedente diário iniciado em segundo plano."},
    )

    response = client.post(
        "/api/v1/adjustments/admin/reprocess-daily-excess",
        json={"start_date": "2026-08-01", "end_date": "2026-08-14", "user_ids": [1], "overwrite_reviewed": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    legacy_response = client.post(
        "/api/v1/adjustments/admin/reprocess-extra-time",
        json={"start_date": "2026-08-01", "end_date": "2026-08-14", "user_ids": [1]},
    )
    assert legacy_response.status_code in (404, 405)


def test_upload_adjustment_attachment(client: TestClient, mocker: MagicMock) -> None:
    expected = AdjustmentAttachmentResponse(
        id=1,
        file_path="uploads/at_1.pdf",
        file_type="application/pdf",
        uploaded_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        AdjustmentService,
        "upload_attachment",
        new_callable=AsyncMock,
        return_value=expected,
    )

    test_file = io.BytesIO(b"fake pdf")
    response = client.post(
        "/api/v1/adjustments/1/attachments",
        files={"file": ("at_1.pdf", test_file, "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["id"] == 1


def test_download_adjustment_attachment(client: TestClient, mocker: MagicMock) -> None:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"fake attachment data")
        temp_path = f.name

    try:
        mocker.patch.object(
            AdjustmentService,
            "get_attachment_file_path",
            new_callable=AsyncMock,
            return_value=(temp_path, "test.pdf"),
        )

        response = client.get("/api/v1/adjustments/1/download")
        assert response.status_code == 200
        assert response.content == b"fake attachment data"
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_read_my_adjustments(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(
        AdjustmentService,
        "get_my_enriched",
        new_callable=AsyncMock,
        return_value=[],
    )

    response = client.get("/api/v1/adjustments/my")
    assert response.status_code == 200
    assert response.json() == []


def test_read_all_adjustments(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(
        AdjustmentService,
        "get_all_enriched",
        new_callable=AsyncMock,
        return_value=[],
    )

    response = client.get("/api/v1/adjustments/")
    assert response.status_code == 200
    assert response.json() == []


def test_approve_adjustment(client: TestClient, mocker: MagicMock) -> None:
    expected = AdjustmentRequestResponse(
        id=1,
        user_id=1,
        user_name="User Test",
        target_date=date(2026, 8, 14),
        adjustment_type=AdjustmentType.FORGOT_PUNCH,
        record_type=RecordType.ENTRY,
        time=time(8, 0),
        status=AdjustmentStatus.APPROVED,
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        AdjustmentService,
        "approve_adjustment",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.put(
        "/api/v1/adjustments/1/approve",
        json={"comment": "Aprovado"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"


def test_reject_adjustment(client: TestClient, mocker: MagicMock) -> None:
    expected = AdjustmentRequestResponse(
        id=1,
        user_id=1,
        user_name="User Test",
        target_date=date(2026, 8, 14),
        adjustment_type=AdjustmentType.FORGOT_PUNCH,
        record_type=RecordType.ENTRY,
        time=time(8, 0),
        status=AdjustmentStatus.REJECTED,
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        AdjustmentService,
        "reject_adjustment",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.put(
        "/api/v1/adjustments/1/reject",
        json={"comment": "Recusado"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_delete_adjustment(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(AdjustmentService, "delete_adjustment", new_callable=AsyncMock)

    response = client.delete("/api/v1/adjustments/1?reason=Exclusao+justificada")
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_admin_delete_adjustment(client: TestClient, mocker: MagicMock) -> None:
    mocker.patch.object(AdjustmentService, "admin_delete_adjustment", new_callable=AsyncMock)

    response = client.delete("/api/v1/adjustments/admin/1?reason=Exclusao+admin+justificada")
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_admin_revert_adjustment_status(client: TestClient, mocker: MagicMock) -> None:
    expected = AdjustmentRequestResponse(
        id=1,
        user_id=1,
        user_name="User Test",
        target_date=date(2026, 8, 14),
        adjustment_type=AdjustmentType.FORGOT_PUNCH,
        record_type=RecordType.ENTRY,
        time=time(8, 0),
        status=AdjustmentStatus.PENDING,
        created_at=datetime(2026, 8, 14, 10, 0, 0),
    )
    mocker.patch.object(
        AdjustmentService,
        "revert_adjustment_status",
        new_callable=AsyncMock,
        return_value=expected,
    )

    response = client.put(
        "/api/v1/adjustments/admin/1/revert-status",
        json={"status": "PENDING", "comment": "Revertendo"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
