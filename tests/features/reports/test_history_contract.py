from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.reports.report_service import ReportService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture
def history_client():
    user = User(id=17, role=UserRole.MANAGER, is_active=True)
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    with TestClient(app) as client:
        yield client, user
    app.dependency_overrides.clear()


@pytest.mark.parametrize('user_id', [None, 17, 23])
def test_history_selects_identity_through_query(history_client, mocker, user_id):
    client, user = history_client
    expected = {'month': 10, 'year': 2026, 'total_worked_time': '00:00', 'days': []}
    history = mocker.patch.object(ReportService, 'get_history_report', new_callable=AsyncMock, return_value=expected)
    query = {'month': 10, 'year': 2026}
    if user_id is not None:
        query['user_id'] = user_id
    response = client.get('/api/v1/reports/history', params=query)
    assert response.status_code == 200
    assert response.json()['days'] == []
    history.assert_awaited_once_with(user_id=17 if user_id is None else user_id, month=10, year=2026, current_user=user)


@pytest.mark.parametrize('query', [
    {'user_id': 0}, {'user_id': -1}, {'user_id': 'invalid'},
    {'month': 0}, {'month': 13}, {'year': 0},
])
def test_history_rejects_invalid_filters(history_client, mocker, query):
    client, _ = history_client
    history = mocker.patch.object(ReportService, 'get_history_report', new_callable=AsyncMock)
    assert client.get('/api/v1/reports/history', params=query).status_code == 422
    history.assert_not_awaited()


def test_history_requires_authentication():
    with TestClient(app) as client:
        assert client.get('/api/v1/reports/history').status_code == 401


def test_employee_cannot_read_someone_elses_history(mocker):
    user = User(id=3, role=UserRole.EMPLOYEE, is_active=True)
    mocker.patch('app.features.reports.report_service.async_user_repository.get',
                 new_callable=AsyncMock, return_value=User(id=4))
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    try:
        with TestClient(app) as client:
            assert client.get('/api/v1/reports/history', params={'user_id': 4}).status_code == 403
    finally:
        app.dependency_overrides.clear()
