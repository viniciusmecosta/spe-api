from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features.time_records.time_record_exceptions import TimeRecordAccessDeniedError
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_repository import (
    AsyncTimeRecordRepository,
    TimeRecordRepository,
)
from app.features.time_records.time_record_schemas import (
    ManualTimeRecordCreate,
    TimeRecordFilters,
)
from app.features.time_records.time_record_service import TimeRecordService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import RecordType, UserRole


@pytest.fixture
def canonical_client():
    user = User(id=1, role=UserRole.EMPLOYEE, is_active=True)
    service = TimeRecordService()
    now = datetime(2026, 11, 1, 8)
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=now, created_at=now)
    service.register_manual_record = AsyncMock(return_value=record)
    service.list_records = AsyncMock(return_value=[record])
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    app.dependency_overrides[TimeRecordService] = lambda: service
    with TestClient(app) as client:
        yield client, service, user
    app.dependency_overrides.clear()


@pytest.mark.parametrize('record_type', ['ENTRY', 'EXIT'])
def test_create_canonical_record(canonical_client, record_type):
    client, service, user = canonical_client
    service.register_manual_record.return_value.record_type = RecordType(record_type)
    response = client.post('/api/v1/time-records', json={'record_type': record_type})
    assert response.status_code == 201
    assert response.json()['record_type'] == record_type
    parameters = service.register_manual_record.await_args.kwargs
    assert parameters['user_id'] == user.id
    assert parameters['record_type'] == RecordType(record_type)
    assert isinstance(parameters['request'], Request)
    assert isinstance(parameters['background_tasks'], BackgroundTasks)


@pytest.mark.parametrize('body', [{}, {'record_type': 'PAUSE'}, {'record_type': 'ENTRY', 'user_id': 2}])
def test_reject_invalid_manual_record(canonical_client, body):
    client, service, _ = canonical_client
    assert client.post('/api/v1/time-records', json=body).status_code == 422
    service.register_manual_record.assert_not_awaited()


def test_list_canonical_records(canonical_client):
    client, service, user = canonical_client
    response = client.get('/api/v1/time-records', params={
        'user_id': 1, 'start_date': '2026-11-01T00:00:00Z',
        'end_date': '2026-11-02T00:00:00Z', 'skip': 2, 'limit': 1000,
    })
    assert response.status_code == 200
    assert response.json()[0]['id'] == 1
    parameters = service.list_records.await_args.kwargs
    assert parameters['current_user'] is user
    assert parameters['filters'].user_id == 1
    assert parameters['filters'].skip == 2
    assert parameters['filters'].limit == 1000
    assert parameters['filters'].start_date.utcoffset() == timedelta(hours=-3)


def test_list_canonical_defaults(canonical_client):
    client, service, _ = canonical_client
    assert client.get('/api/v1/time-records').status_code == 200
    assert service.list_records.await_args.kwargs['filters'] == TimeRecordFilters()


@pytest.mark.parametrize('parameters', [
    {'limit': 0}, {'limit': 1001}, {'skip': -1}, {'user_id': 0}, {'user_id': 2**31},
    {'start_date': 'invalid'}, {'unknown': 'value'},
    {'start_date': '2026-11-02T00:00:00', 'end_date': '2026-11-01T00:00:00'},
])
def test_reject_invalid_list_filters(canonical_client, parameters):
    client, service, _ = canonical_client
    assert client.get('/api/v1/time-records', params=parameters).status_code == 422
    service.list_records.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.MANAGER, UserRole.MAINTAINER])
async def test_manager_list_other_user(role, async_db_mock):
    repository = MagicMock(spec=AsyncTimeRecordRepository)
    repository.get_filtered = AsyncMock(return_value=['record'])
    service = TimeRecordService(db=async_db_mock, repo=repository)
    async_db_mock.sync_session = MagicMock()
    filters = TimeRecordFilters(user_id=2)
    assert await service.list_records(filters=filters, current_user=User(id=1, role=role)) == ['record']
    repository.get_filtered.assert_awaited_once_with(async_db_mock, user_id=2, filters=filters)


@pytest.mark.asyncio
@pytest.mark.parametrize('user_id', [None, 1])
async def test_employee_list_self(user_id, db_session_mock, mocker):
    repository = mocker.patch('app.features.time_records.time_record_service.time_record_repository')
    repository.get_filtered.return_value = ['record']
    filters = TimeRecordFilters(user_id=user_id)
    result = await TimeRecordService().list_records(
        db=db_session_mock, filters=filters, current_user=User(id=1, role=UserRole.EMPLOYEE),
    )
    assert result == ['record']
    repository.get_filtered.assert_called_once_with(db_session_mock, user_id=1, filters=filters)


@pytest.mark.asyncio
async def test_employee_cannot_list_other_user(db_session_mock, mocker):
    repository = mocker.patch('app.features.time_records.time_record_service.time_record_repository')
    with pytest.raises(TimeRecordAccessDeniedError):
        await TimeRecordService(db=db_session_mock).list_records(
            filters=TimeRecordFilters(user_id=2), current_user=User(id=1, role=UserRole.EMPLOYEE),
        )
    repository.get_filtered.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('print_receipt', [True, False])
@pytest.mark.parametrize('record_type', [RecordType.ENTRY, RecordType.EXIT])
async def test_manual_record_transaction(db_session_mock, mocker, print_receipt, record_type):
    service = TimeRecordService(db=db_session_mock)
    now = datetime(2026, 11, 1, 8)
    record = TimeRecord(id=1, user_id=1, record_type=record_type, record_datetime=now, created_at=now)
    register = mocker.patch.object(service, '_register_manual_punch', new_callable=AsyncMock, return_value=record)
    printer = mocker.patch.object(service, 'trigger_auto_print', new_callable=AsyncMock)
    request = MagicMock(spec=Request)
    tasks = BackgroundTasks() if print_receipt else None
    result = await service.register_manual_record(user_id=1, request=request, record_type=record_type, background_tasks=tasks)
    assert result.id == record.id
    register.assert_awaited_once_with(db_session_mock, 1, request, record_type)
    db_session_mock.commit.assert_called_once()
    db_session_mock.rollback.assert_not_called()
    if print_receipt:
        printer.assert_awaited_once_with(db=db_session_mock, record=record, background_tasks=tasks)
    else:
        printer.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_record_failure_rolls_back(db_session_mock, mocker):
    service = TimeRecordService(db=db_session_mock)
    mocker.patch.object(service, '_register_manual_punch', new_callable=AsyncMock, side_effect=TimeRecordAccessDeniedError())
    with pytest.raises(TimeRecordAccessDeniedError):
        await service.register_manual_record(user_id=1, request=MagicMock(spec=Request), record_type=RecordType.ENTRY)
    db_session_mock.rollback.assert_called_once()
    db_session_mock.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,record_type', [('register_entry', RecordType.ENTRY), ('register_exit', RecordType.EXIT)])
async def test_legacy_services_delegate(db_session_mock, mocker, method, record_type):
    service = TimeRecordService()
    register = mocker.patch.object(service, 'register_manual_record', new_callable=AsyncMock, return_value='record')
    request = MagicMock(spec=Request)
    tasks = BackgroundTasks()
    assert await getattr(service, method)(db_session_mock, 1, request, tasks) == 'record'
    register.assert_awaited_once_with(db=db_session_mock, user_id=1, request=request, record_type=record_type, background_tasks=tasks)


@pytest.mark.parametrize('filters', [
    TimeRecordFilters(), TimeRecordFilters(start_date=datetime(2026, 11, 1, 8)),
    TimeRecordFilters(end_date=datetime(2026, 11, 1, 8)),
    TimeRecordFilters(start_date=datetime(2026, 11, 1, 8), end_date=datetime(2026, 11, 1, 8)),
])
def test_filtered_repository(db_session, normal_user, filters):
    now = datetime(2026, 11, 1, 8)
    other_user = User(username="other-user", role=UserRole.EMPLOYEE)
    db_session.add(other_user)
    db_session.flush()
    records = [
        TimeRecord(user_id=normal_user.id, record_type=RecordType.ENTRY, record_datetime=now),
        TimeRecord(user_id=normal_user.id, record_type=RecordType.EXIT, record_datetime=now),
        TimeRecord(user_id=normal_user.id, record_type=RecordType.ENTRY, record_datetime=now, is_ignored=True),
        TimeRecord(user_id=other_user.id, record_type=RecordType.ENTRY, record_datetime=now),
    ]
    db_session.add_all(records)
    db_session.commit()
    result = TimeRecordRepository().get_filtered(db_session, user_id=normal_user.id, filters=filters)
    assert [item.id for item in result] == [records[1].id, records[0].id]
    page = TimeRecordRepository().get_filtered(db_session, user_id=normal_user.id, filters=TimeRecordFilters(skip=1, limit=1))
    assert [item.id for item in page] == [records[0].id]


@pytest.mark.asyncio
async def test_async_filtered_repository(async_db_mock):
    async_db_mock.scalars.return_value = MagicMock()
    async_db_mock.scalars.return_value.all.return_value = ['record']
    assert await AsyncTimeRecordRepository().get_filtered(async_db_mock, user_id=1, filters=TimeRecordFilters()) == ['record']
    statement = async_db_mock.scalars.await_args.args[0]
    assert 'time_records.user_id' in str(statement)
    assert 'time_records.id DESC' in str(statement)


def test_optional_date_and_manual_schema():
    assert TimeRecordFilters(start_date=None, end_date=None).start_date is None
    assert ManualTimeRecordCreate(record_type='ENTRY').record_type == RecordType.ENTRY
    with pytest.raises(ValidationError):
        TimeRecordFilters(start_date=datetime.max)


@pytest.mark.parametrize('start,end,expected', [
    (None, None, [2, 1, 0]), (datetime(2026, 11, 1, 9), None, [2, 1]),
    (None, datetime(2026, 11, 1, 9), [1, 0]),
    (datetime(2026, 11, 1, 9), datetime(2026, 11, 1, 9), [1]),
])
def test_filtered_repository_date_boundaries(db_session, normal_user, start, end, expected):
    records = [
        TimeRecord(user_id=normal_user.id, record_type=RecordType.ENTRY, record_datetime=datetime(2026, 11, 1, hour))
        for hour in (8, 9, 10)
    ]
    db_session.add_all(records)
    db_session.commit()
    result = TimeRecordRepository().get_filtered(
        db_session, user_id=normal_user.id, filters=TimeRecordFilters(start_date=start, end_date=end),
    )
    assert [record.id for record in result] == [records[index].id for index in expected]


def test_canonical_list_does_not_bypass_domain_authorization(canonical_client):
    client, service, _ = canonical_client
    service.list_records.side_effect = TimeRecordAccessDeniedError()
    response = client.get('/api/v1/time-records?user_id=2')
    assert response.status_code == 403


def test_canonical_routes_require_authentication():
    with TestClient(app) as client:
        assert client.get('/api/v1/time-records').status_code == 401
        assert client.post('/api/v1/time-records', json={'record_type': 'ENTRY'}).status_code == 401
