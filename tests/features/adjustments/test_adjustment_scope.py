from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import DomainException
from app.features.adjustments.adjustment_exceptions import AdjustmentPermissionError
from app.features.adjustments.adjustment_service import AdjustmentService
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.mark.parametrize('role', list(UserRole))
async def test_own_scope_uses_authenticated_identity(mocker, role):
    service = AdjustmentService()
    own = mocker.patch.object(service, 'get_my_enriched', new_callable=AsyncMock, return_value=['own'])
    team = mocker.patch.object(service, 'get_all_enriched', new_callable=AsyncMock)
    user = SimpleNamespace(id=7, role=role)
    assert await service.list_adjustments(user, month=3, year=2026, skip=10, limit=20,
                                          status='PENDING', order_by='target_date', order_direction='asc') == ['own']
    own.assert_awaited_once_with(user_id=7, month=3, year=2026, skip=10, limit=20,
                                status='PENDING', order_by='target_date', order_direction='asc')
    team.assert_not_awaited()


@pytest.mark.parametrize('role', [UserRole.MANAGER, UserRole.MAINTAINER])
async def test_team_scope_requires_privileged_actor(mocker, role):
    service = AdjustmentService()
    team = mocker.patch.object(service, 'get_all_enriched', new_callable=AsyncMock, return_value=['team'])
    assert await service.list_adjustments(SimpleNamespace(id=7, role=role), scope='team') == ['team']
    team.assert_awaited_once()


async def test_employee_team_scope_is_denied_before_read(mocker):
    service = AdjustmentService()
    team = mocker.patch.object(service, 'get_all_enriched', new_callable=AsyncMock)
    with pytest.raises(AdjustmentPermissionError):
        await service.list_adjustments(SimpleNamespace(id=7, role=UserRole.EMPLOYEE), scope='team')
    team.assert_not_awaited()


async def test_unknown_service_scope_is_rejected():
    with pytest.raises(DomainException) as error:
        await AdjustmentService().list_adjustments(SimpleNamespace(id=7, role=UserRole.MAINTAINER), scope='unknown')
    assert error.value.status_code == 422


async def test_admin_delete_delegates_transactional_common_service(mocker):
    service = AdjustmentService()
    delete = mocker.patch.object(service, 'delete_adjustment', new_callable=AsyncMock)
    await service.admin_delete_adjustment(adjustment_id=3, admin_id=7, reason='Duplicado')
    delete.assert_awaited_once_with(db=None, adjustment_id=3, manager_id=7, reason='Duplicado')


@pytest.fixture
def scope_client():
    user = SimpleNamespace(id=7, role=UserRole.EMPLOYEE)
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_collection_route_defaults_to_own_scope(scope_client, mocker):
    operation = mocker.patch.object(AdjustmentService, 'list_adjustments', new_callable=AsyncMock, return_value=[])
    response = scope_client.get('/api/v1/adjustments', params={'month': 3, 'year': 2026, 'status': 'PENDING'})
    assert response.status_code == 200
    assert response.history == []
    assert operation.await_args.kwargs['scope'] == 'mine'
    assert operation.await_args.kwargs['current_user'].id == 7
    assert operation.await_args.kwargs['status'] == 'PENDING'


@pytest.mark.parametrize('query', [{'scope': 'unknown'}, {'limit': 101}, {'skip': -1}, {'month': 13}])
def test_collection_route_validates_filters(scope_client, query):
    assert scope_client.get('/api/v1/adjustments', params=query).status_code == 422


def test_employee_cannot_read_team_through_canonical_route(scope_client):
    assert scope_client.get('/api/v1/adjustments', params={'scope': 'team'}).status_code == 403
