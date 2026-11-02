from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features.adjustments.adjustment_schemas import (
    AdjustmentRequestResponse,
    AdjustmentReviewRequest,
)
from app.features.adjustments.adjustment_service import AdjustmentService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import AdjustmentStatus, AdjustmentType, UserRole


@pytest.fixture
def client():
    user = User(id=17, role=UserRole.MANAGER, is_active=True)
    app.dependency_overrides[deps.get_current_manager] = lambda: user
    with TestClient(app) as transport:
        yield transport
    app.dependency_overrides.clear()


@pytest.mark.parametrize('status', ['APPROVED', 'REJECTED'])
def test_review_delegates_to_service(client, mocker, status):
    expected = AdjustmentRequestResponse(
        id=7, user_id=3, user_name='Employee', target_date=date(2026, 8, 14),
        adjustment_type=AdjustmentType.DAILY_EXCESS, amount_hours=1,
        status=AdjustmentStatus(status), created_at=datetime(2026, 8, 14, 10),
    )
    review = mocker.patch.object(AdjustmentService, 'review_adjustment', new_callable=AsyncMock, return_value=expected)
    response = client.put('/api/v1/adjustments/7/review', json={'status': status, 'comment': 'Decisão fundamentada'})
    assert response.status_code == 200
    assert response.json()['status'] == status
    review.assert_awaited_once_with(
        request_id=7, manager_id=17,
        review=AdjustmentReviewRequest(status=status, comment='Decisão fundamentada'),
    )


@pytest.mark.parametrize('payload', [
    {}, {'status': 'PENDING'}, {'status': 'INVALID'},
    {'status': 'REJECTED'}, {'status': 'REJECTED', 'comment': ''},
    {'status': 'REJECTED', 'comment': '  '},
    {'status': 'REJECTED', 'comment': 'Motivo', 'approved_amount_hours': 1},
    {'status': 'APPROVED', 'approved_amount_hours': -1},
    {'status': 'APPROVED', 'manager_id': 99},
])
def test_review_rejects_invalid_contract(client, mocker, payload):
    review = mocker.patch.object(AdjustmentService, 'review_adjustment', new_callable=AsyncMock)
    assert client.put('/api/v1/adjustments/7/review', json=payload).status_code == 422
    review.assert_not_awaited()


@pytest.mark.parametrize('amount', [float('inf'), float('-inf'), float('nan')])
def test_review_rejects_nonfinite_hours(amount):
    with pytest.raises(ValidationError):
        AdjustmentReviewRequest(status='APPROVED', approved_amount_hours=amount)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['APPROVED', 'REJECTED'])
async def test_service_dispatches_review_without_changing_domain_rules(status):
    service = AdjustmentService()
    service.approve_adjustment = AsyncMock(return_value='approved')
    service.reject_adjustment = AsyncMock(return_value='rejected')
    review = AdjustmentReviewRequest(status=status, comment='Motivo', approved_amount_hours=1 if status == 'APPROVED' else None)
    result = await service.review_adjustment(request_id=7, manager_id=17, review=review)
    if status == 'APPROVED':
        assert result == 'approved'
        service.approve_adjustment.assert_awaited_once_with(request_id=7, manager_id=17, comment='Motivo', approved_amount_hours=1)
        service.reject_adjustment.assert_not_awaited()
    else:
        assert result == 'rejected'
        service.reject_adjustment.assert_awaited_once_with(request_id=7, manager_id=17, comment='Motivo')
        service.approve_adjustment.assert_not_awaited()


def test_review_requires_authentication():
    with TestClient(app) as client:
        assert client.put('/api/v1/adjustments/7/review', json={'status': 'APPROVED'}).status_code == 401


def test_employee_cannot_review():
    user = User(id=3, role=UserRole.EMPLOYEE, is_active=True)
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    try:
        with TestClient(app) as client:
            assert client.put('/api/v1/adjustments/7/review', json={'status': 'APPROVED'}).status_code == 403
    finally:
        app.dependency_overrides.clear()
