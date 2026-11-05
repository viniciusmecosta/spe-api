from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_schemas import AdministrativeTimeRecordCreate
from app.features.time_records.time_record_service import TimeRecordService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import RecordType, UserRole


@pytest.fixture
def resource_client():
    user = User(id=17, role=UserRole.MANAGER, is_active=True)
    now = datetime(2026, 11, 1, 8)
    record = TimeRecord(id=7, user_id=3, record_type=RecordType.ENTRY, record_datetime=now, created_at=now)
    service = TimeRecordService()
    service.create_admin_record = AsyncMock(return_value=record)
    service.update_admin_record = AsyncMock(return_value=record)
    service.delete_admin_record = AsyncMock()
    service.toggle_record_type = AsyncMock(return_value=record)
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    app.dependency_overrides[TimeRecordService] = lambda: service
    with TestClient(app) as client:
        yield client, service, user
    app.dependency_overrides.clear()


def admin_record():
    return {'user_id': 3, 'record_type': 'ENTRY', 'record_datetime': '2026-11-01T08:00:00', 'edit_justification': 'Correção aprovada'}


@pytest.mark.parametrize('role', [UserRole.MANAGER, UserRole.MAINTAINER])
def test_administrative_creation_uses_same_collection(resource_client, role):
    client, service, user = resource_client
    user.role = role
    response = client.post('/api/v1/time-records', json=admin_record())
    assert response.status_code == 201
    assert response.json()['user_id'] == 3
    params = service.create_admin_record.await_args.kwargs
    assert isinstance(params['obj_in'], AdministrativeTimeRecordCreate)
    assert params['obj_in'].user_id == 3
    assert params['manager_id'] == user.id


def test_employee_cannot_forge_administrative_creation(resource_client):
    client, service, user = resource_client
    user.role = UserRole.EMPLOYEE
    assert client.post('/api/v1/time-records', json=admin_record()).status_code == 403
    service.create_admin_record.assert_not_awaited()


@pytest.mark.parametrize('changes', [{'user_id': 0}, {'user_id': 2**31}, {'extra': 'forged'}, {'record_datetime': None}])
def test_strict_administrative_creation_validation(resource_client, changes):
    client, service, _ = resource_client
    assert client.post('/api/v1/time-records', json=admin_record() | changes).status_code == 422
    service.create_admin_record.assert_not_awaited()


def test_patch_record_uses_resource_identity(resource_client):
    client, service, user = resource_client
    response = client.patch('/api/v1/time-records/7', json={'record_type': 'EXIT', 'edit_justification': 'Correção aprovada'})
    assert response.status_code == 200
    params = service.update_admin_record.await_args.kwargs
    assert params['record_id'] == 7
    assert params['manager_id'] == user.id
    assert params['obj_in'].record_type == RecordType.EXIT


def test_delete_record_uses_query_without_body(resource_client):
    client, service, user = resource_client
    assert client.delete('/api/v1/time-records/7', params={'justification': 'Registro duplicado'}).status_code == 200
    service.delete_admin_record.assert_awaited_once_with(record_id=7, manager_id=user.id, justification='Registro duplicado', validate_justification=True)


@pytest.mark.parametrize('justification', [None, '', 'tiny', 'x' * 301])
def test_delete_requires_valid_query_justification(resource_client, justification):
    client, service, _ = resource_client
    params = {} if justification is None else {'justification': justification}
    assert client.delete('/api/v1/time-records/7', params=params).status_code == 422
    service.delete_admin_record.assert_not_awaited()


def test_toggle_is_a_posted_transition(resource_client):
    client, service, user = resource_client
    assert client.post('/api/v1/time-records/7/type-transitions').status_code == 200
    service.toggle_record_type.assert_awaited_once_with(record_id=7, current_user=user)


@pytest.mark.parametrize('method,body', [('PATCH', {'edit_justification': 'Registro duplicado'}), ('DELETE', None)])
def test_resource_mutations_require_manager(resource_client, method, body):
    client, _, user = resource_client
    user.role = UserRole.EMPLOYEE
    assert client.request(method, '/api/v1/time-records/7', json=body, params={'justification': 'Registro duplicado'}).status_code == 403
