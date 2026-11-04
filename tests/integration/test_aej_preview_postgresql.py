from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import insert

from app.features.companies.company_models import Company
from app.features.reports.aej_preview_service import AejPreviewService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


async def test_preview_uses_real_schedules_and_markings(pg_session_factory):
    async with pg_session_factory() as session:
        company = Company(name="Empresa", cnpj="12345678000199", address="Rua A")
        employee = User(username="preview-user", name="José", cpf="12345678901", role=UserRole.EMPLOYEE)
        session.add_all([company, employee])
        await session.flush()
        schedule = UserWorkScheduleConfig(user_id=employee.id, day_of_week=0, daily_minutes=480,
                                          entry_1=time(8), exit_1=time(16), valid_from=date(2026, 2, 1))
        session.add(schedule)
        await session.execute(insert(TimeRecord.__table__), [
            {"user_id": employee.id, "record_type": "ENTRY", "record_datetime": datetime(2026, 2, 2, 11, tzinfo=UTC)},
            {"user_id": employee.id, "record_type": "EXIT", "record_datetime": datetime(2026, 2, 2, 19, tzinfo=UTC)},
        ])
        await session.flush()
        response = await AejPreviewService(session).export(employee.id, 2, 2026)
        lines = response.body.decode("iso-8859-1").splitlines()
        assert lines[1] == f"03|{employee.id}|12345678901|José"
        assert lines[2] == f"04|{schedule.id}|480|0800|1600||"
        assert lines[3] == f"05|{employee.id}|2026-02-02T08:00:00-0300||E|001|T|{schedule.id}|"
        assert lines[4] == f"05|{employee.id}|2026-02-02T16:00:00-0300||S|001|T||"
        assert lines[5] == "99|1|0|1|1|2|0|0|0"
