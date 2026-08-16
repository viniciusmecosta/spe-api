from datetime import date, datetime, time
import pytest
from pydantic import ValidationError

from app.features.adjustments.adjustment_schemas import (
    AdjustmentAttachmentResponse,
    AdjustmentRequestCreate,
    AdjustmentRequestResponse,
)
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType


def test_adjustment_request_create_validation_waiver():
    target = date(2026, 1, 1)
    with pytest.raises(ValidationError, match="Abono requer"):
        AdjustmentRequestCreate(
            adjustment_type=AdjustmentType.WAIVER,
            target_date=target,
        )


def test_adjustment_request_create_validation_forgot_punch():
    target = date(2026, 1, 1)
    with pytest.raises(ValidationError, match="tipo"):
        AdjustmentRequestCreate(
            adjustment_type=AdjustmentType.FORGOT_PUNCH,
            target_date=target,
        )


def test_adjustment_request_create_validation_delete_punch():
    target = date(2026, 1, 1)
    t = time(8, 0)
    with pytest.raises(ValidationError, match="requer observação"):
        AdjustmentRequestCreate(
            adjustment_type=AdjustmentType.DELETE_PUNCH,
            target_date=target,
            record_type=RecordType.ENTRY,
            time=t,
        )


def test_adjustment_attachment_response_windows_path():
    now_dt = datetime.now()
    att = AdjustmentAttachmentResponse(
        id=1,
        file_path="uploads\\subfolder\\doc.pdf",
        file_type="pdf",
        uploaded_at=now_dt,
    )
    assert att.url == "/static/doc.pdf"


def test_adjustment_request_response_metadata_extra_time():
    target = date(2026, 1, 1)
    t = time(18, 0)
    now_dt = datetime.now()
    resp = AdjustmentRequestResponse(
        id=1,
        user_id=1,
        user_name="User",
        status=AdjustmentStatus.PENDING,
        adjustment_type=AdjustmentType.EXTRA_TIME,
        target_date=target,
        time=t,
        amount_hours=1.5,
        created_at=now_dt,
    )
    info = resp.metadata_info
    assert info["tempo_extra_minutos"] == 90
    assert info["horario_batido"] == "18:00"
