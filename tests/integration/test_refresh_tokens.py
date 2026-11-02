import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.core.security import get_password_hash
from app.features.auth.auth_models import RefreshToken
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def auth_client(pg_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "prod")
    async with pg_session_factory() as session:
        password_hash = await asyncio.to_thread(get_password_hash, "password123")
        session.add_all(
            [
                User(
                    username="employee",
                    name="Employee",
                    role=UserRole.EMPLOYEE,
                    password_hash=password_hash,
                ),
                User(
                    username="manager",
                    name="Manager",
                    role=UserRole.MANAGER,
                    password_hash=password_hash,
                ),
            ]
        )
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
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def login(client, username="employee", password="password123"):
    response = await client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


def headers(token):
    return {"Authorization": "Bearer " + token["access_token"]}


async def test_rotation_replay_revokes_family_but_preserves_other_login(
    auth_client, pg_session_factory
):
    original = await login(auth_client)
    other = await login(auth_client)
    response = await auth_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != original["refresh_token"]
    async with pg_session_factory() as session:
        tokens = list((await session.scalars(select(RefreshToken))).all())
        assert all(token.token_hash != original["refresh_token"] for token in tokens)
        assert len(tokens) == 3
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(rotated))
    ).status_code == 200
    response = await auth_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert response.status_code == 401
    assert (
        await auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        )
    ).status_code == 401
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(rotated))
    ).status_code == 401
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(other))
    ).status_code == 200


async def test_concurrent_refresh_consumes_token_once(auth_client):
    token = await login(auth_client)
    responses = await asyncio.gather(
        *[
            auth_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]}
            )
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 401]
    success = next(
        response.json() for response in responses if response.status_code == 200
    )
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(success))
    ).status_code == 401


async def test_logout_is_idempotent_and_revokes_access(auth_client):
    token = await login(auth_client)
    for _ in range(2):
        assert (
            await auth_client.post(
                "/api/v1/auth/logout", json={"refresh_token": token["refresh_token"]}
            )
        ).status_code == 204
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(token))
    ).status_code == 401
    assert (
        await auth_client.post("/api/v1/auth/logout", json={"refresh_token": "x" * 64})
    ).status_code == 204


async def test_admin_requires_password_change_restricts_login_and_change_restores_access(
    auth_client,
):
    employee = await login(auth_client)
    employee_id = (
        await auth_client.get("/api/v1/auth/me", headers=headers(employee))
    ).json()["id"]
    manager = await login(auth_client, "manager")
    response = await auth_client.put(
        f"/api/v1/users/{employee_id}",
        headers=headers(manager),
        json={"password_change_required": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["password_change_required"] is True
    assert (
        await auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": employee["refresh_token"]}
        )
    ).status_code == 401
    restricted = await login(auth_client)
    assert restricted["password_change_required"] is True
    assert restricted["refresh_token"] is None
    payload = jwt.decode(
        restricted["access_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    assert payload["purpose"] == "password_change"
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(restricted))
    ).status_code == 200
    response = await auth_client.get("/api/v1/users/me", headers=headers(restricted))
    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"
    response = await auth_client.post(
        "/api/v1/auth/password",
        headers=headers(restricted),
        json={"current_password": "password123", "new_password": "newpassword123"},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["password_change_required"] is False
    assert updated["refresh_token"]
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(restricted))
    ).status_code == 401
    response = await auth_client.get("/api/v1/users/me", headers=headers(updated))
    assert response.status_code == 200
    assert response.json()["password_change_required"] is False
    assert (
        await auth_client.post(
            "/api/v1/auth/login",
            data={"username": "employee", "password": "password123"},
        )
    ).status_code == 401
    await login(auth_client, password="newpassword123")


async def test_password_change_revokes_every_other_session(auth_client):
    original = await login(auth_client)
    other = await login(auth_client)
    response = await auth_client.post(
        "/api/v1/auth/password",
        headers=headers(original),
        json={"current_password": "password123", "new_password": "newpassword123"},
    )
    assert response.status_code == 200
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(original))
    ).status_code == 401
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(other))
    ).status_code == 401
    assert (
        await auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": other["refresh_token"]}
        )
    ).status_code == 401
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(response.json()))
    ).status_code == 200


async def test_refresh_rejects_expired_and_inactive_users(
    auth_client, pg_session_factory
):
    token = await login(auth_client)
    async with pg_session_factory() as session:
        await session.execute(
            update(RefreshToken).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        await session.commit()
    assert (
        await auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]}
        )
    ).status_code == 401
    token = await login(auth_client)
    async with pg_session_factory() as session:
        await session.execute(
            update(User).where(User.username == "employee").values(is_active=False)
        )
        await session.commit()
    assert (
        await auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]}
        )
    ).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"current_password": "wrong", "new_password": "validpass123"},
        {"current_password": "password123", "new_password": "password123"},
        {"current_password": "password123", "new_password": "short"},
    ],
)
async def test_password_change_rejects_invalid_input_without_revoking_session(
    auth_client, changes
):
    token = await login(auth_client)
    assert (
        await auth_client.post(
            "/api/v1/auth/password", headers=headers(token), json=changes
        )
    ).status_code in (401, 422)
    assert (
        await auth_client.get("/api/v1/auth/me", headers=headers(token))
    ).status_code == 200


async def test_purge_only_removes_expired_rows_in_bounded_batches(
    auth_client, pg_session_factory
):
    from app.features.auth.auth_repository import auth_repository

    await login(auth_client)
    await login(auth_client)
    await login(auth_client)
    now = datetime.now(UTC)
    async with pg_session_factory() as session:
        tokens = list(
            (
                await session.scalars(select(RefreshToken).order_by(RefreshToken.id))
            ).all()
        )
        tokens[0].expires_at = now - timedelta(seconds=2)
        tokens[1].expires_at = now - timedelta(seconds=1)
        tokens[2].used_at = now
        tokens[2].revoked_at = now
        await session.commit()
        assert await auth_repository.purge_expired(session, now, batch_size=1) == 1
        await session.commit()
        assert len(list((await session.scalars(select(RefreshToken))).all())) == 2
        assert await auth_repository.purge_expired(session, now) == 1
        await session.commit()
        remaining = list((await session.scalars(select(RefreshToken))).all())
        assert len(remaining) == 1
        assert remaining[0].revoked_at is not None
        assert remaining[0].used_at is not None
