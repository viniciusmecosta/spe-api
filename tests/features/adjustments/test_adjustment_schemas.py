from datetime import date, datetime, time

from pydantic import ValidationError

import pytest
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


def test_adjustment_request_response_metadata_daily_excess():
    target = date(2026, 1, 1)
    now_dt = datetime.now()
    resp = AdjustmentRequestResponse(
        id=2,
        user_id=1,
        user_name="User",
        status=AdjustmentStatus.APPROVED,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        target_date=target,
        amount_hours=2.0,
        approved_amount_hours=1.5,
        reason_text="Excesso de jornada",
        created_at=now_dt,
    )
    info = resp.metadata_info
    assert info["tempo_excedente_minutos"] == 120
    assert info["tempo_aprovado_minutos"] == 90
    assert info["motivo"] == "Excesso de jornada"


def test_adjustment_request_response_metadata_waiver_and_punch():
    target = date(2026, 1, 1)
    now_dt = datetime.now()
    resp_waiver = AdjustmentRequestResponse(
        id=3,
        user_id=1,
        user_name="User",
        status=AdjustmentStatus.APPROVED,
        adjustment_type=AdjustmentType.WAIVER,
        target_date=target,
        amount_hours=8.0,
        created_at=now_dt,
    )
    assert resp_waiver.metadata_info == {"horas_abonadas": 8.0}

    resp_punch = AdjustmentRequestResponse(
        id=4,
        user_id=1,
        user_name="User",
        status=AdjustmentStatus.PENDING,
        adjustment_type=AdjustmentType.PUNCH_NOT_COUNTED,
        target_date=target,
        record_type=RecordType.ENTRY,
        time=time(8, 30),
        created_at=now_dt,
    )
    assert resp_punch.metadata_info["horario_solicitado"] == "08:30"
    assert resp_punch.metadata_info["tipo_batida"] == "ENTRY"


def test_adjustment_request_metadata_info_fallback():
    target = date(2026, 1, 1)
    now_dt = datetime.now()
    resp = AdjustmentRequestResponse(
        id=5,
        user_id=1,
        user_name="User",
        status=AdjustmentStatus.PENDING,
        adjustment_type=AdjustmentType.OTHER,
        target_date=target,
        created_at=now_dt,
    )
    assert resp.metadata_info == {}


def test_adjustment_request_create_validation_forgot_punch_missing_time():
    target = date(2026, 1, 1)
    with pytest.raises(ValidationError, match="Ajuste de ponto requer"):
        AdjustmentRequestCreate(
            adjustment_type=AdjustmentType.FORGOT_PUNCH,
            target_date=target,
            record_type=RecordType.ENTRY,
            time=None,
        )
