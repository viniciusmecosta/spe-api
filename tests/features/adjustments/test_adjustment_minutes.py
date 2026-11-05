from datetime import date

import pytest
from pydantic import ValidationError

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.adjustments.adjustment_schemas import (
    AdjustmentReviewRequest,
    AdjustmentWaiverCreate,
)
from app.main import app
from app.shared.enums import AdjustmentStatus


def test_model_converts_hours_to_integer_minutes_half_up():
    assert app
    adjustment = AdjustmentRequest(amount_hours=1.025, approved_amount_hours=0)
    assert adjustment.amount_minutes == 62
    assert adjustment.approved_amount_minutes == 0
    assert adjustment.amount_hours == 62 / 60
    adjustment.amount_hours = None
    adjustment.approved_amount_hours = None
    assert adjustment.amount_minutes is None
    assert adjustment.approved_amount_minutes is None


def test_request_accepts_integer_minutes():
    waiver = AdjustmentWaiverCreate(user_id=1, target_date=date(2026, 1, 1), amount_minutes=61, reason_text='Teste')
    review = AdjustmentReviewRequest(status=AdjustmentStatus.APPROVED, approved_amount_minutes=1)
    assert waiver.amount_hours == 61 / 60
    assert review.approved_amount_hours == 1 / 60


@pytest.mark.parametrize('value', [1.5, True, '2'])
def test_request_rejects_non_integer_minutes(value):
    with pytest.raises(ValidationError):
        AdjustmentReviewRequest(status=AdjustmentStatus.APPROVED, approved_amount_minutes=value)


def test_request_rejects_conflicting_units():
    with pytest.raises(ValidationError):
        AdjustmentReviewRequest(status=AdjustmentStatus.APPROVED, approved_amount_minutes=60, approved_amount_hours=1)
