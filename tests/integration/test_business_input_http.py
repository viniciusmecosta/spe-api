import httpx
import pytest
import pytest_asyncio
from api_workflow_support import DAY, PERIOD, ApiWorkflow, seed_root
from sqlalchemy import func, select

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def api(pg_session_factory):
    await seed_root(pg_session_factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        flow = ApiWorkflow(client)
        flow.headers = await flow.login("qa_root")
        yield flow


async def test_invalid_waivers_and_failed_approval_do_not_create_approved_adjustments(api, pg_session_factory):
    user_id = await api.create_employee()
    payload = {"user_id": user_id, "target_date": DAY, "amount_hours": 1, "reason_text": "Atestado sintetico"}
    await api.request("POST", "/adjustments/admin/waive", 404, json={**payload, "user_id": 999999})
    for amount in [0, -1, 10.5]:
        await api.request("POST", "/adjustments/admin/waive", 422, json={**payload, "amount_hours": amount})
    request = await api.json("POST", "/adjustments/", 201, headers=api.employee_headers, json={
        "adjustment_type": "WAIVER", "target_date": DAY, "amount_hours": 1, "reason_text": "Atestado sintetico",
    })
    await api.request("PUT", f"/adjustments/{request['id']}/approve", 400)
    async with pg_session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(AdjustmentRequest))
        assert count == 1
        saved = await session.get(AdjustmentRequest, request["id"])
        assert saved.status.value == "PENDING"


async def test_business_boundaries_and_reprocessing_are_rejected_without_creating_jobs(api, pg_session_factory):
    from app.features.system.system_models import BackgroundJob

    user_id = await api.create_employee()
    await api.request("POST", "/daily-summaries/admin/reprocess", 400, json={
        "start_date": "2026-09-30", "end_date": "2026-09-01", "user_ids": [user_id],
    })
    await api.request("POST", "/daily-summaries/admin/reprocess", 404, json={
        "start_date": DAY, "end_date": DAY, "user_ids": [999999],
    })
    await api.request("POST", "/daily-summaries/admin/reprocess", 422, json={
        "start_date": DAY, "end_date": DAY, "user_ids": [],
    })
    await api.request("POST", "/payroll/close", 422, json={"month": 13, "year": 2026})
    await api.request("GET", "/reports/history/me", 422, params={**PERIOD, "month": 0})
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 0


async def test_waiver_limit_and_duplicate_holiday_are_enforced(api, pg_session_factory):
    user_id = await api.create_employee()
    payload = {"user_id": user_id, "target_date": DAY, "amount_hours": 6, "reason_text": "Abono sintetico"}
    await api.request("POST", "/adjustments/admin/waive", 201, json=payload)
    await api.request("POST", "/adjustments/admin/waive", 400, json={**payload, "amount_hours": 5})
    await api.request("POST", "/holidays/", 201, json={"date": "2026-09-01", "name": "Feriado sintetico"})
    await api.request("POST", "/holidays/", 400, json={"date": "2026-09-01", "name": "Feriado duplicado"})
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(AdjustmentRequest)) == 1


async def test_employee_cannot_access_other_employees_records(api):
    user_id = await api.create_employee()
    await api.request("PUT", f"/users/{user_id}", json={"can_export_report": False})
    other = await api.json("POST", "/users/", 201, json={
        "username": "qa_other", "name": "Colaborador Beta", "password": "Synthetic-flow-password-123",
    })
    record = await api.add_punch(other["id"], "ENTRY", "08:00")
    for path in [f"/reports/history/user/{other['id']}", f"/reports/user/{other['id']}",
                 f"/timesheets/user/{other['id']}/pdf", f"/time-records/receipt/{record['short_id']}"]:
        await api.request("GET", path, 403, headers=api.employee_headers, params=PERIOD)
    assert user_id != other["id"]
