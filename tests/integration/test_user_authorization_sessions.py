import asyncio

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def authorized_client(pg_session_factory, monkeypatch):
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'prod')
    async with pg_session_factory() as session:
        password_hash = await asyncio.to_thread(get_password_hash, 'password123')
        actors = {role: User(username=role.value.lower(), name=role.value,
                            role=role, password_hash=password_hash, is_active=True)
                  for role in UserRole}
        session.add_all(actors.values())
        await session.commit()

    async def database():
        async with pg_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[deps.get_async_db] = database
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            yield client, actors
    finally:
        app.dependency_overrides.clear()


def authorization(user):
    return {'Authorization': 'Bearer ' + create_access_token(user.id, auth_version=user.auth_version)}


async def test_manager_cannot_create_or_promote_maintainer(authorized_client):
    client, actors = authorized_client
    manager = actors[UserRole.MANAGER]
    response = await client.post('/api/v1/users/', headers=authorization(manager), json={
        'username': 'elevated', 'password': 'password123', 'role': 'MAINTAINER'})
    assert response.status_code == 403
    for target in (manager, actors[UserRole.EMPLOYEE]):
        response = await client.put(f'/api/v1/users/{target.id}', headers=authorization(manager),
                                    json={'role': 'MAINTAINER'})
        assert response.status_code == 403
    assert (await client.get('/api/v1/routine-logs/', headers=authorization(manager))).status_code == 403


async def test_last_maintainer_is_protected_and_second_allows_demotion(authorized_client):
    client, actors = authorized_client
    admin = actors[UserRole.MAINTAINER]
    for changes in ({'role': 'EMPLOYEE'}, {'is_active': False}):
        response = await client.put(f'/api/v1/users/{admin.id}', headers=authorization(admin), json=changes)
        assert response.status_code == 403
    response = await client.post('/api/v1/users/', headers=authorization(admin), json={
        'username': 'second_admin', 'password': 'password123', 'role': 'MAINTAINER'})
    assert response.status_code == 201
    response = await client.put(f'/api/v1/users/{admin.id}', headers=authorization(admin), json={'role': 'MANAGER'})
    assert response.status_code == 200


async def test_password_reset_revokes_old_tokens_and_new_login_works(authorized_client):
    client, actors = authorized_client
    employee = actors[UserRole.EMPLOYEE]
    old_headers = authorization(employee)
    response = await client.put('/api/v1/users/me', headers=old_headers, json={'password': 'new-password123'})
    assert response.status_code == 200
    response = await client.get('/api/v1/auth/me', headers=old_headers)
    assert response.status_code == 401
    response = await client.post('/api/v1/auth/login', data={'username': employee.username, 'password': 'new-password123'})
    assert response.status_code == 200
    response = await client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + response.json()['access_token']})
    assert response.status_code == 200


@pytest.mark.parametrize('password', ['x', 'a' * 73, 'á' * 37])
async def test_password_boundaries_return_validation_error(authorized_client, password):
    client, actors = authorized_client
    response = await client.put('/api/v1/users/me', headers=authorization(actors[UserRole.EMPLOYEE]), json={'password': password})
    assert response.status_code == 422
