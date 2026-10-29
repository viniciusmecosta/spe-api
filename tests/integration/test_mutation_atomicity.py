from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from api_workflow_support import DAY, PASSWORD, ApiWorkflow, fixed_clock, seed_root
from sqlalchemy import select

from app.features.companies.company_models import Company
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.devices.device_models import DeviceCredential
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.printers.printer_models import Printer
from app.features.system.audit_service import audit_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User

pytestmark = pytest.mark.asyncio

COMPANY_INPUT = {
    "name": "Empresa Sintetica",
    "cnpj": "12345678000195",
    "address": "Rua de Teste, 100",
}
RESOURCE_MODELS = {
    "company": Company,
    "holiday": Holiday,
    "printer": Printer,
    "credential": DeviceCredential,
    "user": User,
    "record": TimeRecord,
}


@pytest_asyncio.fixture
async def mutation_api(pg_session_factory, monkeypatch):
    from app.main import app
    from app.shared.trusted_time_service import trusted_time_service

    await seed_root(pg_session_factory)
    monkeypatch.setattr(trusted_time_service, "get_trusted_time", fixed_clock)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        flow = ApiWorkflow(client)
        flow.headers = await flow.login("qa_root")
        yield flow


async def prepare_create(api, resource):
    if resource == "company":
        return "/companies/", COMPANY_INPUT, 200
    if resource == "holiday":
        return "/holidays/", {"date": DAY, "name": "Feriado Sintetico"}, 201
    if resource == "printer":
        company = await api.json("POST", "/companies/", json=COMPANY_INPUT)
        return "/printers/", {
            "name": "Impressora Sintetica", "address": "127.0.0.1",
            "company_id": company["id"], "status": False,
        }, 201
    if resource == "credential":
        return "/device-credentials/", {
            "name": "Dispositivo Sintetico", "key_type": "DEVICE",
            "api_key": "synthetic-mutation-device-key",
        }, 201
    if resource == "user":
        return "/users/", {
            "username": "qa_mutation_employee", "name": "Colaborador Sintetico",
            "password": PASSWORD,
        }, 201
    user_id = await api.create_employee()
    return "/time-records/admin", {
        "user_id": user_id, "record_type": "ENTRY",
        "record_datetime": f"{DAY}T08:00:00-03:00",
        "edit_justification": "Inclusao sintetica para teste de atomicidade",
    }, 201


async def snapshot(factory, resource):
    models = [RESOURCE_MODELS[resource]]
    if resource in {"record", "holiday"}:
        models.append(DailySummary)
    values = {}
    async with factory() as session:
        for model in models:
            columns = [column for column in model.__table__.columns
                       if column.name not in {"password_hash", "api_key_hash"}]
            rows = await session.execute(select(*columns).order_by(model.id))
            values[model.__tablename__] = [tuple(row) for row in rows]
    return values


def fail_audit(monkeypatch):
    failure = AsyncMock(side_effect=RuntimeError("synthetic audit unavailable"))
    monkeypatch.setattr(audit_service, "async_log_change", failure)
    return failure


@pytest.mark.parametrize("resource", RESOURCE_MODELS)
async def test_create_rolls_back_when_audit_fails(
    mutation_api, pg_session_factory, monkeypatch, resource,
):
    path, payload, _ = await prepare_create(mutation_api, resource)
    before = await snapshot(pg_session_factory, resource)
    audit = fail_audit(monkeypatch)

    await mutation_api.request("POST", path, 500, json=payload)

    audit.assert_awaited_once()
    assert await snapshot(pg_session_factory, resource) == before


@pytest.mark.parametrize("resource", ["company", "printer", "credential", "user", "record"])
async def test_update_rolls_back_when_audit_fails(
    mutation_api, pg_session_factory, monkeypatch, resource,
):
    path, payload, status = await prepare_create(mutation_api, resource)
    created = await mutation_api.json("POST", path, status, json=payload)
    update_path = path if resource == "company" else f"{path.rstrip('/')}/{created['id']}"
    method = "PATCH" if resource == "printer" else "PUT"
    update = {"name": "Nome Sintetico Atualizado"}
    if resource == "record":
        update = {
            "record_datetime": f"{DAY}T09:00:00-03:00",
            "edit_justification": "Edicao sintetica para teste de atomicidade",
        }
    before = await snapshot(pg_session_factory, resource)
    audit = fail_audit(monkeypatch)

    await mutation_api.request(method, update_path, 500, json=update)

    audit.assert_awaited_once()
    assert await snapshot(pg_session_factory, resource) == before


@pytest.mark.parametrize("resource", ["holiday", "printer", "credential", "record"])
async def test_delete_rolls_back_when_audit_fails(
    mutation_api, pg_session_factory, monkeypatch, resource,
):
    path, payload, status = await prepare_create(mutation_api, resource)
    created = await mutation_api.json("POST", path, status, json=payload)
    delete_path = f"{path.rstrip('/')}/{created['id']}"
    body = {}
    if resource == "record":
        body = {"json": {"edit_justification": "Exclusao sintetica para teste de atomicidade"}}
    before = await snapshot(pg_session_factory, resource)
    audit = fail_audit(monkeypatch)

    await mutation_api.request("DELETE", delete_path, 500, **body)

    audit.assert_awaited_once()
    assert await snapshot(pg_session_factory, resource) == before


@pytest.mark.parametrize(("resource", "field"), [
    ("company", "name"), ("company", "cnpj"), ("company", "address"),
    ("company", "auto_print_receipt"),
    ("printer", "name"), ("printer", "address"), ("printer", "company_id"),
    ("printer", "status"), ("printer", "paper_width"),
    ("credential", "name"), ("credential", "is_active"), ("user", "username"),
])
async def test_explicit_null_for_required_storage_field_is_rejected(
    mutation_api, pg_session_factory, resource, field,
):
    path, payload, status = await prepare_create(mutation_api, resource)
    created = await mutation_api.json("POST", path, status, json=payload)
    update_path = path if resource == "company" else f"{path.rstrip('/')}/{created['id']}"
    method = "PATCH" if resource == "printer" else "PUT"
    before = await snapshot(pg_session_factory, resource)

    await mutation_api.request(method, update_path, 422, json={field: None})

    assert await snapshot(pg_session_factory, resource) == before


@pytest.mark.parametrize(("action", "failure"), [("close", "audit"), ("close", "queue"), ("reopen", "audit")])
async def test_payroll_rolls_back_when_audit_fails(
    mutation_api, pg_session_factory, monkeypatch, tmp_path, action, failure,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    period = {"month": 9, "year": 2026}
    if action == "reopen":
        await mutation_api.request("POST", "/payroll/close", json=period)
    async with pg_session_factory() as session:
        before = (await session.execute(select(PayrollClosure.id, PayrollClosure.deleted_at))).all()
    files_before = {path.name for path in tmp_path.rglob("*") if path.is_file()}
    if failure == "audit":
        fail_audit(monkeypatch)
    else:
        from app.features.payroll.payroll_service import PayrollService

        monkeypatch.setattr(PayrollService, "_queue_notification", AsyncMock(side_effect=RuntimeError("queue failure")))
    payload = period if action == "close" else {**period, "observation": "Teste sintetico"}

    await mutation_api.request("POST", f"/payroll/{action}", 500, json=payload)

    async with pg_session_factory() as session:
        after = (await session.execute(select(PayrollClosure.id, PayrollClosure.deleted_at))).all()
    assert after == before
    assert {path.name for path in tmp_path.rglob("*") if path.is_file()} == files_before
