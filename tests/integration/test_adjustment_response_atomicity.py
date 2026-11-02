from datetime import date, time

import httpx
import pytest
from sqlalchemy import func, select

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.system.system_models import AuditLog
from app.features.users.user_models import User
from app.shared import deps
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType, UserRole

pytestmark = pytest.mark.asyncio


async def seed_waiver_users(factory):
    async with factory() as session:
        manager = User(username="response-manager", name="Gestor Sintetico", role=UserRole.MAINTAINER)
        employee = User(username="response-employee", name="Colaborador Alfa", role=UserRole.EMPLOYEE)
        session.add_all([manager, employee])
        await session.commit()
        return manager, employee


async def post_waiver(manager, employee):
    from app.main import app

    app.dependency_overrides[deps.get_current_manager] = lambda: manager
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/v1/adjustments/admin/waive",
                json={
                    "user_id": employee.id,
                    "target_date": "2026-10-27",
                    "amount_hours": 2,
                    "reason_text": "Abono de teste sintetico",
                },
            )
    finally:
        app.dependency_overrides.pop(deps.get_current_manager, None)


async def test_waiver_returns_success_with_the_committed_adjustment(pg_session_factory):
    manager, employee = await seed_waiver_users(pg_session_factory)
    response = await post_waiver(manager, employee)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["user_name"] == "Colaborador Alfa"
    assert payload["status"] == "APPROVED"
    assert payload["attachments"] == []
    assert payload["metadata_info"] == {"horas_abonadas": 2}
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(AdjustmentRequest)) == 1
        row = await session.get(AdjustmentRequest, payload["id"])
        assert row.amount_hours == 2
        summary = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == employee.id, DailySummary.apuration_date == date(2026, 10, 27)
        ))
        assert summary.waiver_minutes == 120
        assert await session.scalar(select(func.count()).select_from(AuditLog)) == 1


async def test_invalid_waiver_response_rolls_back_the_whole_operation(pg_session_factory, monkeypatch):
    manager, employee = await seed_waiver_users(pg_session_factory)
    monkeypatch.setattr(AdjustmentRequest, "user_name", property(lambda self: None))
    response = await post_waiver(manager, employee)
    assert response.status_code == 500
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(AdjustmentRequest)) == 0
        assert await session.scalar(select(func.count()).select_from(DailySummary)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditLog)) == 0


async def test_waiver_accepts_a_user_without_an_optional_display_name(pg_session_factory):
    manager, employee = await seed_waiver_users(pg_session_factory)
    async with pg_session_factory() as session:
        row = await session.get(User, employee.id)
        row.name = None
        await session.commit()
    response = await post_waiver(manager, employee)
    assert response.status_code == 201, response.text
    assert response.json()["user_name"] == "Desconhecido"


@pytest.mark.parametrize("operation", ["create", "approve", "reject", "revert"])
async def test_adjustment_mutations_return_serializable_responses(pg_session_factory, operation):
    from app.main import app

    manager, employee = await seed_waiver_users(pg_session_factory)
    async with pg_session_factory() as session:
        adjustment = AdjustmentRequest(
            user_id=employee.id, target_date=date(2026, 10, 27),
            adjustment_type=AdjustmentType.FORGOT_PUNCH, record_type=RecordType.ENTRY,
            time=time(8), status=AdjustmentStatus.PENDING,
        )
        session.add(adjustment)
        await session.commit()
        adjustment_id = adjustment.id
    dependencies = [deps.get_current_manager, deps.get_current_maintainer, deps.get_current_active_user]
    for dependency in dependencies:
        app.dependency_overrides[dependency] = lambda: manager
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            if operation == "create":
                response = await client.post("/api/v1/adjustments/", json={
                    "adjustment_type": "FORGOT_PUNCH", "target_date": "2026-10-27",
                    "record_type": "EXIT", "time": "17:00:00",
                })
            elif operation == "revert":
                response = await client.put(f"/api/v1/adjustments/admin/{adjustment_id}/revert-status",
                                            json={"status": "REJECTED", "comment": "Teste sintetico"})
            else:
                body = {"comment": "Teste sintetico"}
                response = await client.put(f"/api/v1/adjustments/{adjustment_id}/{operation}", json=body)
        assert response.status_code in {200, 201}, response.text
        assert response.json()["attachments"] == []
        assert response.json()["user_name"] in {"Gestor Sintetico", "Colaborador Alfa"}
    finally:
        for dependency in dependencies:
            app.dependency_overrides.pop(dependency, None)
