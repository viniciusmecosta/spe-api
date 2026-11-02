import httpx
import pytest
from api_workflow_support import ApiWorkflow, seed_root

from app.main import app

pytestmark = pytest.mark.asyncio


async def test_nonexistent_configuration_references_are_rejected(pg_session_factory):
    await seed_root(pg_session_factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        api = ApiWorkflow(client)
        api.headers = await api.login("qa_root")
        company = await api.json("POST", "/companies/", 200, json={
            "name": "Empresa Sintetica", "cnpj": "12345678000195", "address": "Rua Teste",
        })
        await api.request("PUT", "/companies/", 422, json={"default_printer_id": 999999})
        await api.request("POST", "/printers/", 422, json={
            "name": "Impressora Sintetica", "address": "127.0.0.1", "company_id": 999999,
        })
        printer = await api.json("POST", "/printers/", 201, json={
            "name": "Impressora Sintetica", "address": "127.0.0.1", "company_id": company["id"],
        })
        await api.request("PATCH", f"/printers/{printer['id']}", 422, json={"company_id": 999999})
