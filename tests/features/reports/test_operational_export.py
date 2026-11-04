import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.features.reports.operational_export_service import (
    EXPORT_BATCH_SIZE,
    OperationalExportService,
)
from app.features.reports.report_exceptions import ReportUserNotFoundError
from app.main import app
from app.shared import deps
from app.shared.document_authenticity import (
    compute_operational_export_authenticity_hash,
)
from app.shared.document_signature import verify_document
from app.shared.enums import RecordType, UserRole


async def response_bytes(response):
    if hasattr(response, "body_iterator"):
        return b"".join([chunk async for chunk in response.body_iterator])
    return response.body


@pytest.fixture
def session():
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=7, name="Pessoa")
    db.scalars.return_value = MagicMock()
    db.scalars.return_value.all.return_value = []
    return db


@pytest.mark.asyncio
async def test_operational_records_include_deleted_and_authenticity_hash(session):
    record = SimpleNamespace(
        id=42, record_datetime=datetime(2026, 2, 1, 12, tzinfo=UTC),
        record_type=RecordType.ENTRY, device_name="Relógio", is_ignored=True,
        deleted_at=datetime(2026, 2, 2, 12, tzinfo=UTC),
        original_record_id=41, source_adjustment_id=None,
    )
    active_record = SimpleNamespace(**vars(record))
    active_record.deleted_at = None
    session.scalars.return_value.all.return_value = [record, active_record]
    response = await OperationalExportService(session).export("marcacoes", 7, 2, 2026, MagicMock())
    body = await response_bytes(response)
    data = json.loads(body)
    assert verify_document(body).authentic
    unsigned = {key: value for key, value in data.items() if key != "assinatura_spe"}
    assert data["metadados"]["hash_dados"] == "sha256:" + compute_operational_export_authenticity_hash(unsigned)
    assert int(response.headers["content-length"]) == len(body)
    assert "aviso" not in data
    assert data["metadados"]["hash_dados"].startswith("sha256:")
    assert data["periodo"] == {"inicio": "2026-02-01", "fim": "2026-02-28"}
    assert data["marcacoes"][0]["excluida_em"] is not None
    assert data["marcacoes"][0]["registro_original_id"] == 41
    assert data["marcacoes"][1]["excluida_em"] is None
    assert response.headers["cache-control"] == "no-store"
    assert "operacional_marcacoes_7_202602.json" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_operational_journey_uses_existing_report(session):
    report = MagicMock()
    report.model_dump.return_value = {"daily_details": [{"date": "2026-02-01"}]}
    with patch("app.features.reports.operational_export_service.ReportService") as report_service:
        report_service.return_value.get_advanced_user_report_or_404 = AsyncMock(return_value=report)
        response = await OperationalExportService(session).export("jornada", 7, 2, 2026, MagicMock())
    body = await response_bytes(response)
    data = json.loads(body)
    assert data["tipo"] == "jornada"
    assert data["jornada"]["daily_details"][0]["date"] == "2026-02-01"
    report_service.return_value.get_advanced_user_report_or_404.assert_awaited_once()


@pytest.mark.asyncio
async def test_operational_export_rejects_unknown_user(session):
    session.get.return_value = None
    service = OperationalExportService(session)
    actor = MagicMock()
    with pytest.raises(ReportUserNotFoundError):
        await service.export("marcacoes", 7, 2, 2026, actor)


@pytest.mark.asyncio
async def test_operational_export_all_employees_with_one_query(session):
    record = SimpleNamespace(
        id=42, user_id=7, record_datetime=datetime(2026, 2, 1, 12, tzinfo=UTC),
        record_type=RecordType.ENTRY, device_name="Relógio", is_ignored=False,
        deleted_at=None, original_record_id=None, source_adjustment_id=None,
    )
    result = MagicMock()
    result.all.return_value = [(record, "Pessoa")]
    session.execute.return_value = result
    response = await OperationalExportService(session).export("marcacoes", None, 2, 2026, MagicMock())
    body = await response_bytes(response)
    data = json.loads(body)
    assert data["usuario"] is None
    assert data["marcacoes"][0]["usuario"] == {"id": 7, "nome": "Pessoa"}
    assert "operacional_marcacoes_todos_202602.json" in response.headers["content-disposition"]
    session.get.assert_not_awaited()
    session.scalars.assert_not_awaited()
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_operational_journey_requires_employee(session):
    service = OperationalExportService(session)
    actor = MagicMock()
    with pytest.raises(HTTPException) as error:
        await service.export("jornada", None, 2, 2026, actor)
    assert error.value.status_code == 422
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_collective_export_paginates_without_losing_equal_timestamps(session):
    timestamp = datetime(2026, 2, 1, 12, tzinfo=UTC)
    def record(number):
        return SimpleNamespace(
            id=number, user_id=7, record_datetime=timestamp,
            record_type=RecordType.ENTRY, device_name="Relógio", is_ignored=False,
            deleted_at=None, original_record_id=None, source_adjustment_id=None,
        )
    first = MagicMock()
    first.all.return_value = [(record(i), "Pessoa") for i in range(1, EXPORT_BATCH_SIZE + 1)]
    second = MagicMock()
    second.all.return_value = [(record(EXPORT_BATCH_SIZE + 1), "Pessoa")]
    session.execute.side_effect = [first, second]
    response = await OperationalExportService(session).export("marcacoes", None, 2, 2026, MagicMock())
    body = await response_bytes(response)
    data = json.loads(body)
    assert [r["id"] for r in data["marcacoes"]] == list(range(1, EXPORT_BATCH_SIZE + 2))
    assert session.execute.await_count == 2


def test_operational_export_requires_manager():
    employee = MagicMock(id=7, role=UserRole.EMPLOYEE, is_active=True)
    app.dependency_overrides[deps.get_current_active_user] = lambda: employee
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/reports/operational-export?user_id=7&month=2&year=2026&kind=marcacoes")
            collective = client.get("/api/v1/reports/operational-export?month=2&year=2026&kind=marcacoes")
        assert response.status_code == 403
        assert collective.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_operational_export_route_passes_filters():
    manager = MagicMock(id=1, role=UserRole.MANAGER, is_active=True)
    service = MagicMock()
    service.export = AsyncMock(return_value=Response(content="{}", media_type="application/json"))
    app.dependency_overrides[deps.get_current_manager] = lambda: manager
    app.dependency_overrides[OperationalExportService] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/reports/operational-export?user_id=7&month=2&year=2026&kind=jornada")
            invalid = client.get("/api/v1/reports/operational-export?user_id=7&month=2&year=2026&kind=afd")
        assert response.status_code == 200
        assert invalid.status_code == 422
        service.export.assert_awaited_once_with(kind="jornada", user_id=7, month=2, year=2026, user=manager)
    finally:
        app.dependency_overrides.clear()


def test_operational_export_route_allows_collective_records():
    manager = MagicMock(id=1, role=UserRole.MANAGER, is_active=True)
    service = MagicMock()
    service.export = AsyncMock(return_value=Response(content='{}', media_type='application/json'))
    app.dependency_overrides[deps.get_current_manager] = lambda: manager
    app.dependency_overrides[OperationalExportService] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/reports/operational-export?month=2&year=2026&kind=marcacoes')
        assert response.status_code == 200
        service.export.assert_awaited_once_with(kind='marcacoes', user_id=None, month=2, year=2026, user=manager)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_operational_export_spools_to_disk_and_closes_after_download(session, monkeypatch):
    from app.features.reports import operational_export_service

    monkeypatch.setattr(operational_export_service, "EXPORT_MEMORY_LIMIT", 16)
    response = await OperationalExportService(session).export("marcacoes", 7, 2, 2026, MagicMock())
    file = response.body_iterator.ag_frame.f_locals["file"]
    assert file._rolled
    body = await response_bytes(response)
    assert file.closed
    assert verify_document(body).authentic
    data = json.loads(body)
    unsigned = {key: value for key, value in data.items() if key != "assinatura_spe"}
    assert data["metadados"]["hash_dados"] == "sha256:" + compute_operational_export_authenticity_hash(unsigned)


@pytest.mark.asyncio
async def test_operational_export_closes_spool_when_query_fails(session, monkeypatch):
    from contextlib import contextmanager
    from tempfile import TemporaryFile

    from app.features.reports import operational_export_service

    opened = []

    @contextmanager
    def test_file():
        with TemporaryFile(mode="w+b") as file:
            opened.append(file)
            yield file

    monkeypatch.setattr(operational_export_service, "_export_file", test_file)
    session.scalars.side_effect = RuntimeError("database failure")
    service = OperationalExportService(session)
    actor = MagicMock()
    with pytest.raises(RuntimeError, match="database failure"):
        await service.export("marcacoes", 7, 2, 2026, actor)
    assert opened[0].closed


@pytest.mark.asyncio
async def test_interrupted_download_closes_temporary_file(session, monkeypatch):
    from app.features.reports import operational_export_service

    monkeypatch.setattr(operational_export_service, "EXPORT_READ_SIZE", 16)
    response = await OperationalExportService(session).export("marcacoes", 7, 2, 2026, MagicMock())
    file = response.body_iterator.ag_frame.f_locals["file"]
    assert await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert file.closed


def test_operational_download_over_http_is_signed():
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=7, name="Pessoa")
    db.scalars.return_value = MagicMock()
    db.scalars.return_value.all.return_value = []
    app.dependency_overrides[deps.get_current_manager] = lambda: MagicMock(role=UserRole.MANAGER)
    app.dependency_overrides[OperationalExportService] = lambda: OperationalExportService(db)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/reports/operational-export?user_id=7&month=2&year=2026&kind=marcacoes")
        assert response.status_code == 200
        assert verify_document(response.content).authentic
        assert json.loads(response.content)["marcacoes"] == []
    finally:
        app.dependency_overrides.clear()
