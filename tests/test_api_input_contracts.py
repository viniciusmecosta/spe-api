from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.exceptions import setup_exception_handlers
from app.features.timesheets.anomaly_service import AnomalyService
from app.features.users.user_exceptions import BulkScheduleValidationError
from app.features.users.user_models import User
from app.features.users.user_schemas import BulkWorkScheduleCreate, WorkScheduleBase
from app.features.users.user_work_schedule_service import UserWorkScheduleService
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def validated_client():
    session = AsyncMock()
    actor = User(id=1, username='maintainer-validation', role=UserRole.MAINTAINER, is_active=True)

    async def database():
        yield session

    app.dependency_overrides[deps.get_current_active_user] = lambda: actor
    app.dependency_overrides[deps.get_async_db] = database
    client = TestClient(app)
    try:
        yield client, session
    finally:
        client.close()
        app.dependency_overrides.clear()


@pytest.mark.parametrize('path', [
    '/audit/?skip=-1',
    '/audit/?skip=9223372036854775808',
    '/audit/?limit=0',
    '/routine-logs/?limit=-1',
    '/routine-logs/?limit=1001',
    '/users/?after_id=2147483648',
    '/time-records/my?skip=-1',
    '/time-records/my?limit=0',
    '/reports/history/me?month=1&year=10000',
    '/reports/history/user/1?month=1&year=9999',
    '/reports/team-hours?month=1&year=10000',
    '/reports/user/1?month=1&year=10000',
    '/reports/export/excel?month=1&year=9999',
    '/timesheets/user/1/pdf?month=1&year=10000',
    '/timesheets/all/pdf?month=1&year=9999',
    '/anomalies/all?month=13&year=2026',
    '/anomalies/user/1?month=0&year=2026',
    '/anomalies/all?month=1&year=10000',
    '/payroll/?year=10000',
    '/adjustments/my?month=1&year=10000',
    '/adjustments/?month=1&year=10000',
])
def test_invalid_query_is_rejected_before_database_access(validated_client, path):
    client, session = validated_client
    response = client.get('/api/v1' + path)
    assert response.status_code == 422, response.text
    session.execute.assert_not_awaited()
    session.scalar.assert_not_awaited()
    session.scalars.assert_not_awaited()


@pytest.mark.parametrize('path', ['/reports/export/excel', '/timesheets/all/pdf'])
@pytest.mark.parametrize('selection', ['invalid', '1,invalid', '0', '-1', '', '2147483648', '9' * 5000])
def test_invalid_employee_filter_cannot_broaden_export(validated_client, path, selection):
    client, session = validated_client
    response = client.get('/api/v1' + path, params={'month': 1, 'year': 2026, 'employee_ids': selection})
    assert response.status_code == 422, response.text
    session.scalars.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.parametrize('field,value', [('month', 0), ('month', 13), ('year', 10000), ('year', 9999)])
def test_invalid_payroll_competence_is_rejected(validated_client, field, value):
    client, session = validated_client
    payload = {'month': 1, 'year': 2026, field: value}
    response = client.post('/api/v1/payroll/close', json=payload)
    assert response.status_code == 422, response.text
    session.scalars.assert_not_awaited()


def test_largest_supported_report_year_is_accepted(validated_client, mocker):
    client, _ = validated_client
    get_anomalies = mocker.patch.object(AnomalyService, 'get_anomalies_by_month', new_callable=AsyncMock, return_value=[])
    response = client.get('/api/v1/anomalies/all?month=12&year=9998')
    assert response.status_code == 200, response.text
    assert get_anomalies.await_args.kwargs['year'] == 9998


@pytest.mark.parametrize('day', [-1, 7])
def test_schedule_day_is_validated_at_api_boundary(validated_client, day):
    client, session = validated_client
    response = client.post('/api/v1/schedules/bulk', json={
        'valid_from': '2026-10-01', 'valid_until': '2026-10-31',
        'users': [{'user_id': 1, 'schedules': [{'day_of_week': day, 'daily_hours': 8}]}],
    })
    assert response.status_code == 422, response.text
    session.execute.assert_not_awaited()


def test_schedule_reversed_dates_are_rejected_in_body(validated_client):
    client, session = validated_client
    response = client.post('/api/v1/schedules/bulk', json={
        'valid_from': '2026-10-31', 'valid_until': '2026-10-01', 'users': [],
    })
    assert response.status_code == 422, response.text
    session.execute.assert_not_awaited()


@pytest.mark.parametrize('method', ['get', 'put', 'delete'])
def test_schedule_reversed_dates_are_rejected_in_path(validated_client, method):
    client, session = validated_client
    kwargs = {}
    if method == 'put':
        kwargs['json'] = {'valid_from': '2026-10-01', 'valid_until': '2026-10-31', 'users': []}
    response = getattr(client, method)('/api/v1/schedules/bulk/2026-10-31/2026-10-01', **kwargs)
    assert response.status_code == 422, response.text
    assert response.json()['detail'] == 'A data inicial não pode ser maior que a data final.'
    session.execute.assert_not_awaited()


def test_schedule_schema_preserves_valid_overnight_shift_and_same_day_period():
    schedule = WorkScheduleBase(day_of_week=6, daily_hours=8, entry_1='22:00', exit_1='06:00',
                                valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 1))
    assert schedule.entry_1.hour == 22
    assert schedule.exit_1.hour == 6
    assert BulkWorkScheduleCreate(valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 1), users=[])
    invalid_start, invalid_end = date(2026, 10, 2), date(2026, 10, 1)
    with pytest.raises(ValidationError):
        WorkScheduleBase(day_of_week=0, daily_hours=8, valid_from=invalid_start, valid_until=invalid_end)


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['add', 'update'])
@pytest.mark.parametrize('invalid', ['day', 'period'])
async def test_direct_schedule_service_rejects_invalid_input_before_writing(operation, invalid):
    session = AsyncMock()
    service = UserWorkScheduleService(session)
    payload = {'valid_from': date(2026, 10, 1), 'valid_until': date(2026, 10, 31),
               'users': [{'user_id': 1, 'schedules': [{'day_of_week': 0, 'daily_hours': 8}]}]}
    if invalid == 'day':
        payload['users'][0]['schedules'][0]['day_of_week'] = 7
    else:
        payload['valid_from'], payload['valid_until'] = payload['valid_until'], payload['valid_from']
    arguments = {'bulk_data': payload, 'current_user_id': 1}
    action = service.bulk_add_schedules
    if operation == 'update':
        action = service.update_bulk_schedules
        arguments.update(old_valid_from=date(2026, 10, 1), old_valid_until=date(2026, 10, 31))
    with pytest.raises(BulkScheduleValidationError):
        await action(**arguments)
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.parametrize('status,headers', [
    (401, {'WWW-Authenticate': 'Bearer'}),
    (429, {'Retry-After': '30'}),
])
def test_http_exception_handler_preserves_protocol_headers(status, headers):
    application = FastAPI()
    setup_exception_handlers(application)

    @application.get('/error')
    async def fail():
        raise HTTPException(status_code=status, detail='Falha controlada.', headers=headers)

    with TestClient(application) as client:
        response = client.get('/error')
    assert response.status_code == status
    for name, value in headers.items():
        assert response.headers[name] == value
