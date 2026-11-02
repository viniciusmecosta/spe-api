from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from app.features.payroll.payroll_exceptions import (
    PayrollAlreadyClosedError,
    PayrollNotClosedError,
    PayrollPermissionError,
)
from app.features.payroll.payroll_schemas import (
    PayrollCloseTransition,
    PayrollClosureResponse,
    PayrollReopenTransition,
    PayrollTransitionRequest,
    PayrollTransitionResponse,
)
from app.features.payroll.payroll_service import PayrollService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def transition_client():
    actor = User(id=1, username="maintainer", role=UserRole.MAINTAINER, is_active=True)
    service = MagicMock(spec=PayrollService)
    service.transition_period = AsyncMock()
    app.dependency_overrides[deps.get_current_manager] = lambda: actor
    app.dependency_overrides[PayrollService] = lambda: service
    with TestClient(app) as client:
        yield client, service, actor
    app.dependency_overrides.clear()


@pytest.mark.parametrize('action,body', [('CLOSE', {'action': 'CLOSE'}), ('REOPEN', {'action': 'REOPEN', 'observation': 'Correção de registros'})])
def test_transition_contract(transition_client, action, body):
    client, service, actor = transition_client
    closure = PayrollClosureResponse(month=9, year=2026, id=1, is_closed=True) if action == 'CLOSE' else None
    service.transition_period.return_value = PayrollTransitionResponse(
        year=2026, month=9, action=action, is_closed=action == 'CLOSE', closure=closure,
    )
    response = client.post('/api/v1/payroll/2026/9/transitions', json=body)
    assert response.status_code == 200
    assert response.json()['action'] == action
    assert response.json()['is_closed'] == (action == 'CLOSE')
    parameters = service.transition_period.await_args.kwargs
    assert parameters['year'] == 2026
    assert parameters['month'] == 9
    assert parameters['current_user'] is actor
    assert isinstance(parameters['background_tasks'], BackgroundTasks)
    assert parameters['transition'].action == action


@pytest.mark.parametrize('body', [
    {}, {'action': 'INVALID'}, {'action': 'REOPEN'}, {'action': 'REOPEN', 'observation': ''},
    {'action': 'REOPEN', 'observation': '  '}, {'action': 'REOPEN', 'observation': 'a' * 1001},
    {'action': 'CLOSE', 'observation': 'inapplicable'}, {'action': 'CLOSE', 'year': 2026},
    {'action': 'REOPEN', 'observation': 'valid', 'is_closed': False},
])
def test_invalid_transition_body(transition_client, body):
    client, service, _ = transition_client
    assert client.post('/api/v1/payroll/2026/9/transitions', json=body).status_code == 422
    service.transition_period.assert_not_awaited()


@pytest.mark.parametrize('year,month', [(1999, 1), (9999, 1), (2026, 0), (2026, 13), ('invalid', 1)])
def test_invalid_transition_period(transition_client, year, month):
    client, service, _ = transition_client
    assert client.post(f'/api/v1/payroll/{year}/{month}/transitions', json={'action': 'CLOSE'}).status_code == 422
    service.transition_period.assert_not_awaited()


def test_transition_requires_authentication():
    with TestClient(app) as client:
        assert client.post('/api/v1/payroll/2026/9/transitions', json={'action': 'CLOSE'}).status_code == 401


@pytest.mark.parametrize('error', [PayrollAlreadyClosedError("Already closed"), PayrollNotClosedError("Not closed"), PayrollPermissionError("Forbidden")])
def test_domain_errors_preserved(transition_client, error):
    client, service, _ = transition_client
    service.transition_period.side_effect = error
    response = client.post('/api/v1/payroll/2026/9/transitions', json={'action': 'CLOSE'})
    assert response.status_code == error.status_code


@pytest.mark.asyncio
async def test_close_dispatch_keeps_existing_transaction(db_session_mock, mocker):
    service = PayrollService(db=db_session_mock)
    expected = PayrollClosureResponse(id=1, month=9, year=2026, is_closed=True)
    close = mocker.patch.object(service, 'close_period', new_callable=AsyncMock, return_value=expected)
    reopen = mocker.patch.object(service, 'reopen_period', new_callable=AsyncMock)
    actor = User(id=1, role=UserRole.MANAGER)
    tasks = BackgroundTasks()
    result = await service.transition_period(
        year=2026, month=9, transition=PayrollCloseTransition(action='CLOSE'), current_user=actor, background_tasks=tasks,
    )
    assert result.closure == expected
    assert result.action == 'CLOSE'
    assert result.is_closed is True
    parameters = close.await_args.kwargs
    assert parameters['period'].year == 2026
    assert parameters['period'].month == 9
    assert parameters['current_user'] is actor
    assert parameters['background_tasks'] is tasks
    reopen.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_dispatch_preserves_justification(db_session_mock, mocker):
    service = PayrollService(db=db_session_mock)
    close = mocker.patch.object(service, 'close_period', new_callable=AsyncMock)
    reopen = mocker.patch.object(service, 'reopen_period', new_callable=AsyncMock)
    actor = User(id=1, role=UserRole.MAINTAINER)
    tasks = BackgroundTasks()
    result = await service.transition_period(
        year=2026, month=9, transition=PayrollReopenTransition(action='REOPEN', observation='  Correção  '),
        current_user=actor, background_tasks=tasks,
    )
    assert result.closure is None
    assert result.is_closed is False
    parameters = reopen.await_args.kwargs
    assert parameters['period'].observation == 'Correção'
    assert parameters['period'].year == 2026
    assert parameters['period'].month == 9
    assert parameters['current_user'] is actor
    assert parameters['background_tasks'] is tasks
    close.assert_not_awaited()


@pytest.mark.asyncio
async def test_manager_cannot_reopen_through_canonical_dispatch(db_session_mock):
    with pytest.raises(PayrollPermissionError):
        await PayrollService(db=db_session_mock).transition_period(
            year=2026, month=9, transition=PayrollReopenTransition(action='REOPEN', observation='Correção'),
            current_user=User(id=1, role=UserRole.MANAGER), background_tasks=BackgroundTasks(),
        )
    db_session_mock.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_employee_cannot_close_through_dispatch(db_session_mock):
    with pytest.raises(PayrollPermissionError):
        await PayrollService(db=db_session_mock).transition_period(
            year=2026, month=9, transition=PayrollCloseTransition(action='CLOSE'),
            current_user=User(id=1, role=UserRole.EMPLOYEE), background_tasks=BackgroundTasks(),
        )


def test_discriminated_schema():
    adapter = TypeAdapter(PayrollTransitionRequest)
    assert isinstance(adapter.validate_python({'action': 'CLOSE'}), PayrollCloseTransition)
    assert isinstance(adapter.validate_python({'action': 'REOPEN', 'observation': 'Correction'}), PayrollReopenTransition)
    with pytest.raises(ValidationError):
        adapter.validate_python({'action': 'REOPEN', 'observation': None})
