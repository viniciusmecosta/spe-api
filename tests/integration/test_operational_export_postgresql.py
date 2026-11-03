from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import insert

from app.core.config import settings
from app.features.reports.operational_export_service import OperationalExportService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


async def test_operational_export_filters_local_month_and_deleted_records(pg_session_factory, monkeypatch):
    import json

    monkeypatch.setattr(settings, "TIMEZONE", "America/Fortaleza")
    async with pg_session_factory() as session:
        employee = User(username="operational-user", name="Pessoa", role=UserRole.EMPLOYEE)
        session.add(employee)
        await session.flush()
        await session.execute(insert(TimeRecord.__table__), [
            {"user_id": employee.id, "record_type": "ENTRY", "record_datetime": datetime(2026, 2, 1, 2, 59, tzinfo=UTC), "deleted_at": None},
            {"user_id": employee.id, "record_type": "ENTRY", "record_datetime": datetime(2026, 2, 1, 3, tzinfo=UTC), "deleted_at": None},
            {"user_id": employee.id, "record_type": "EXIT", "record_datetime": datetime(2026, 3, 1, 2, 59, tzinfo=UTC),
             "deleted_at": datetime(2026, 3, 2, tzinfo=UTC)},
            {"user_id": employee.id, "record_type": "ENTRY", "record_datetime": datetime(2026, 3, 1, 3, tzinfo=UTC), "deleted_at": None},
        ])
        await session.flush()
        result = await OperationalExportService(session).export(
            "marcacoes", employee.id, 2, 2026, MagicMock(),
        )
        records = json.loads(result.body)["marcacoes"]
        assert len(records) == 2
        assert records[0]["data_hora"].startswith("2026-02-01T00:00:00")
        assert records[1]["data_hora"].startswith("2026-02-28T23:59:00")
        assert records[1]["excluida_em"] is not None

        other = User(username="operational-other", name="Outra pessoa", role=UserRole.EMPLOYEE)
        session.add(other)
        await session.flush()
        await session.execute(insert(TimeRecord.__table__).values(
            user_id=other.id, record_type="ENTRY", record_datetime=datetime(2026, 2, 2, 12, tzinfo=UTC),
        ))
        result = await OperationalExportService(session).export("marcacoes", None, 2, 2026, MagicMock())
        collective = json.loads(result.body)["marcacoes"]
        assert [item["usuario"]["id"] for item in collective] == [employee.id, other.id, employee.id]
        assert collective[1]["usuario"]["nome"] == "Outra pessoa"
        assert collective[-1]["excluida_em"] is not None
