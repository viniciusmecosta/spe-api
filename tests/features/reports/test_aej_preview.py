from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.features.reports.aej_preview_service import (
    AejPreviewService,
    _field,
    _schedule_for_day,
)
from app.features.reports.report_exceptions import ReportUserNotFoundError
from app.main import app
from app.shared import deps
from app.shared.enums import RecordType, UserRole


@pytest.fixture
def db():
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=7, name="José", cpf="123.456.789-01")
    company = SimpleNamespace(name="Empresa", cnpj="12.345.678/0001-99")
    schedule = SimpleNamespace(id=3, day_of_week=0, valid_from=date(2026, 2, 1), valid_until=None,
                               daily_minutes=480, entry_1=time(8), exit_1=time(12), entry_2=time(13), exit_2=time(17))
    record = SimpleNamespace(id=1, user_id=7, record_datetime=datetime(2026, 2, 2, 12, 1, 37, tzinfo=UTC),
                             record_type=RecordType.ENTRY, is_ignored=False, deleted_at=None, edited_by=None,
                             original_record_id=None, source_adjustment_id=None, edit_justification=None)
    company_result, schedule_result, record_result = MagicMock(), MagicMock(), MagicMock()
    company_result.first.return_value = company
    schedule_result.all.return_value = [schedule]
    record_result.all.return_value = [record]
    db.results = [company_result, schedule_result, record_result]
    db.scalars.side_effect = db.results
    return db


@pytest.mark.asyncio
async def test_preview_uses_actual_data_and_states_limitations(db):
    response = await AejPreviewService(db).export(7, 2, 2026)
    lines = response.body.decode("iso-8859-1").split("\r\n")
    assert lines[0].startswith("01|1|12345678000199|||")
    assert lines[1] == "03|7|12345678901|José"
    assert lines[2] == "04|3|480|0800|1200|1300|1700"
    assert lines[3] == "05|7|2026-02-02T09:01:00-0300||E|1|T|3|"
    assert lines[4] == "99|1|0|1|1|1|0|0|0"
    assert response.headers["x-export-status"] == "draft-not-fiscal-unsigned-incomplete"
    assert "nao_fiscal" in response.headers["content-disposition"]
    assert b"ASSINATURA_DIGITAL" not in response.body


@pytest.mark.asyncio
async def test_preview_no_invented_missing_cpf_or_schedule(db):
    db.get.return_value.cpf = None
    db.results[1].all.return_value = []
    response = await AejPreviewService(db).export(7, 2, 2026)
    lines = response.body.decode("iso-8859-1").splitlines()
    assert lines[1] == "03|7||José"
    assert lines[2] == "05|7|2026-02-02T09:01:00-0300||E|1|T||"
    assert lines[3] == "99|1|0|1|0|1|0|0|0"


@pytest.mark.asyncio
async def test_preview_unknown_employee_and_missing_company(db):
    db.get.return_value = None
    with pytest.raises(ReportUserNotFoundError):
        await AejPreviewService(db).export(7, 2, 2026)
    db.get.return_value = SimpleNamespace(id=7)
    db.results[0].first.return_value = None
    with pytest.raises(HTTPException) as error:
        await AejPreviewService(db).export(7, 2, 2026)
    assert error.value.status_code == 422


def test_preview_refuses_delimiters_and_ambiguous_schedules():
    with pytest.raises(HTTPException):
        _field("Nome|falso")
    day = date(2026, 2, 2)
    schedule = SimpleNamespace(day_of_week=0, valid_from=day, valid_until=day)
    assert _schedule_for_day([schedule, schedule], day) is None
    assert _schedule_for_day([schedule], date(2026, 2, 3)) is None


def test_preview_route_only_allows_maintainer():
    app.dependency_overrides[deps.get_current_active_user] = lambda: MagicMock(role=UserRole.MANAGER, is_active=True)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/reports/aej-preview?user_id=7&month=2&year=2026")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_preview_represents_ignored_and_manual_records(db):
    original = db.results[2].all.return_value[0]
    ignored = SimpleNamespace(**vars(original))
    ignored.id = 2
    ignored.is_ignored = True
    ignored.edited_by = 1
    ignored.edit_justification = "Ajuste autorizado"
    exit_record = SimpleNamespace(**vars(original))
    exit_record.id = 3
    exit_record.record_type = RecordType.EXIT
    exit_record.source_adjustment_id = 4
    exit_record.edit_justification = "Incluído pelo gestor"
    db.results[2].all.return_value = [original, ignored, exit_record]
    response = await AejPreviewService(db).export(7, 2, 2026)
    lines = response.body.decode("iso-8859-1").splitlines()
    assert "05|7|2026-02-02T09:01:00-0300||D|1|I||Ajuste autorizado" in lines
    assert "05|7|2026-02-02T09:01:00-0300||S|1|I||Incluído pelo gestor" in lines


@pytest.mark.asyncio
async def test_preview_rejects_characters_not_supported_by_layout(db):
    db.get.return_value.name = "Nome 🐈"
    with pytest.raises(HTTPException) as error:
        await AejPreviewService(db).export(7, 2, 2026)
    assert error.value.status_code == 422
    assert "ISO-8859-1" in error.value.detail


@pytest.mark.asyncio
async def test_preview_paginates_records_with_same_timestamp(db, monkeypatch):
    from app.features.reports import aej_preview_service

    monkeypatch.setattr(aej_preview_service, "BATCH_SIZE", 1)
    first = db.results[2].all.return_value[0]
    second = SimpleNamespace(**vars(first))
    second.id = 2
    second.record_type = RecordType.EXIT
    page2, page3 = MagicMock(), MagicMock()
    page2.all.return_value = [second]
    page3.all.return_value = []
    db.scalars.side_effect = [*db.results, page2, page3]
    response = await AejPreviewService(db).export(7, 2, 2026)
    lines = response.body.decode("iso-8859-1").splitlines()
    assert len([line for line in lines if line.startswith("05|")]) == 2
    assert lines[-1] == "99|1|0|1|1|2|0|0|0"


def test_preview_route_passes_employee_and_period():
    from fastapi.responses import Response

    service = MagicMock()
    service.export = AsyncMock(return_value=Response(content=b"preview"))
    app.dependency_overrides[deps.get_current_maintainer] = lambda: MagicMock(role=UserRole.MAINTAINER)
    app.dependency_overrides[AejPreviewService] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/reports/aej-preview?user_id=7&month=2&year=2026")
        assert response.status_code == 200
        assert response.content == b"preview"
        service.export.assert_awaited_once_with(7, 2, 2026)
    finally:
        app.dependency_overrides.clear()
