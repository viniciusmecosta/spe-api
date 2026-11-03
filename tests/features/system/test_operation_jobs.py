from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from app.features.system.job_schemas import (
    BackupOperationRequest,
    OperationJobRequest,
    ReportOperationRequest,
)
from app.features.system.routine_orchestrator import RoutineOrchestrator
from app.features.system.system_exceptions import OperationPermissionError
from app.features.system.telegram_service import TelegramService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def operation_client(async_db_mock, mocker):
    user = User(id=7, username='maintainer', role=UserRole.MAINTAINER, is_active=True)
    app.dependency_overrides[deps.get_current_maintainer] = lambda: user
    app.dependency_overrides[deps.get_async_db] = lambda: async_db_mock
    record_job = mocker.patch.object(RoutineOrchestrator, '_record_manual_job', new_callable=AsyncMock, return_value=42)
    with TestClient(app) as client:
        yield client, user, record_job
    app.dependency_overrides.clear()


@pytest.mark.parametrize('operation,routine_type,audit_action', [
    ('BACKUP_EMAIL', 'EMAIL_MANUAL_BACKUP', 'MANUAL_BACKUP_EMAIL'),
    ('BACKUP_TELEGRAM', 'TELEGRAM_MANUAL_BACKUP', 'MANUAL_BACKUP_TELEGRAM'),
    ('REPORT_TELEGRAM', 'TELEGRAM_MANUAL_REPORT', 'MANUAL_REPORT_TELEGRAM'),
])
def test_typed_job_admission_preserves_queue_and_audit(operation_client, operation, routine_type, audit_action):
    client, user, record_job = operation_client
    body = {'operation': operation}
    if operation == 'REPORT_TELEGRAM':
        body.update(start_date='2026-08-01', end_date='2026-08-05')
    response = client.post('/api/v1/operations/jobs', json=body)
    assert response.status_code == 202
    result = response.json()
    assert result['job_id'] == '42'
    assert result['status_url'] == '/api/v1/routine-logs/jobs/42'
    assert result['message']
    assert set(result) <= {'job_id', 'message', 'status_url', 'status'}
    arguments = record_job.await_args.args
    assert arguments[0:3] == (routine_type, audit_action, user)
    if operation == 'REPORT_TELEGRAM':
        assert arguments[4:] == (date(2026, 8, 1), date(2026, 8, 5))
    else:
        assert len(arguments) == 4


@pytest.mark.parametrize('body', [
    {}, {'operation': 'DELETE_DATABASE'}, {'operation': 'REPORT_EMAIL'},
    {'operation': 'BACKUP_EMAIL', 'start_date': '2026-08-01'},
    {'operation': 'BACKUP_TELEGRAM', 'end_date': '2026-08-01'},
    {'operation': 'BACKUP_EMAIL', 'user_id': 1}, {'operation': 'REPORT_TELEGRAM'},
    {'operation': 'REPORT_TELEGRAM', 'start_date': '2026-08-01'},
    {'operation': 'REPORT_TELEGRAM', 'start_date': 'invalid', 'end_date': '2026-08-01'},
    {'operation': 'REPORT_TELEGRAM', 'start_date': '2026-08-01', 'end_date': '9999-01-01'},
    {'operation': 'REPORT_TELEGRAM', 'start_date': '2026-08-01', 'end_date': '2026-08-02', 'channel': 'EMAIL'},
])
def test_invalid_operation_contract_rejected_before_queueing(operation_client, body):
    client, _, record_job = operation_client
    assert client.post('/api/v1/operations/jobs', json=body).status_code == 422
    record_job.assert_not_awaited()


@pytest.mark.parametrize('start,end', [('2026-08-05', '2026-08-01'), ('2026-08-01', '2026-08-15')])
def test_existing_report_domain_date_rules_preserved(operation_client, start, end):
    client, _, record_job = operation_client
    response = client.post('/api/v1/operations/jobs', json={
        'operation': 'REPORT_TELEGRAM', 'start_date': start, 'end_date': end,
    })
    assert response.status_code == 400
    record_job.assert_not_awaited()


@pytest.mark.parametrize('role', [UserRole.EMPLOYEE, UserRole.MANAGER])
def test_jobs_are_maintainer_only(role, mocker):
    app.dependency_overrides[deps.get_current_active_user] = lambda: User(id=1, role=role, is_active=True)
    submit = mocker.patch.object(RoutineOrchestrator, 'submit_manual_job', new_callable=AsyncMock)
    try:
        with TestClient(app) as client:
            response = client.post('/api/v1/operations/jobs', json={'operation': 'BACKUP_EMAIL'})
        assert response.status_code == 403
        submit.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


def test_jobs_require_authentication():
    with TestClient(app) as client:
        assert client.post('/api/v1/operations/jobs', json={'operation': 'BACKUP_EMAIL'}).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.EMPLOYEE, UserRole.MANAGER])
async def test_orchestrator_rejects_unprivileged_callers(role, mocker):
    service = RoutineOrchestrator()
    enqueue = mocker.patch.object(service, '_record_manual_job', new_callable=AsyncMock)
    operation = BackupOperationRequest(operation='BACKUP_EMAIL')
    actor = User(id=1, role=role)
    telegram_svc = TelegramService()
    with pytest.raises(OperationPermissionError):
        await service.submit_manual_job(
            operation=operation,
            current_user=actor, audit_svc=None, telegram_svc=telegram_svc,
        )
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_admission_propagates_without_success(mocker):
    service = RoutineOrchestrator()
    enqueue = mocker.patch.object(service, '_record_manual_job', new_callable=AsyncMock, side_effect=RuntimeError('queue unavailable'))
    operation = BackupOperationRequest(operation='BACKUP_TELEGRAM')
    actor = User(id=1, role=UserRole.MAINTAINER)
    telegram_svc = TelegramService()
    with pytest.raises(RuntimeError, match='queue unavailable'):
        await service.submit_manual_job(
            operation=operation,
            current_user=actor, audit_svc=None, telegram_svc=telegram_svc,
        )
    enqueue.assert_awaited_once()


def test_discriminated_contract_exposes_only_supported_operations():
    adapter = TypeAdapter(OperationJobRequest)
    assert isinstance(adapter.validate_python({'operation': 'BACKUP_EMAIL'}), BackupOperationRequest)
    assert isinstance(adapter.validate_python({'operation': 'REPORT_TELEGRAM', 'start_date': '2026-08-01', 'end_date': '2026-08-02'}), ReportOperationRequest)
    with pytest.raises(ValidationError):
        adapter.validate_python({'operation': 'REPORT_TELEGRAM', 'start_date': None, 'end_date': None})


@pytest.mark.parametrize('path', ['/backup/trigger', '/telegram/manual-backup', '/telegram/manual-report'])
def test_legacy_manual_routes_are_removed(path):
    assert 'post' not in app.openapi()['paths'].get('/api/v1' + path, {})
