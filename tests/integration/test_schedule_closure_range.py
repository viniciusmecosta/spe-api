from datetime import date, datetime

import pytest
from sqlalchemy import event

from app.core.security import get_password_hash
from app.features.payroll.payroll_models import PayrollClosure
from app.features.users.user_exceptions import SchedulePayrollClosedError
from app.features.users.user_models import User
from app.features.users.user_work_schedule_service import UserWorkScheduleService
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


async def test_long_schedule_period_checks_closed_months_with_one_query(pg_session_factory):
    async with pg_session_factory() as session:
        statements = []
        engine = session.bind.sync_engine
        def collect(_conn, _cursor, statement, _parameters, _context, _many):
            if 'payroll_closures' in statement:
                statements.append(statement)
        event.listen(engine, 'before_cursor_execute', collect)
        try:
            service = UserWorkScheduleService(session)
            await service.check_payroll_closure(session, date(2000, 1, 1), date(2025, 12, 31))
        finally:
            event.remove(engine, 'before_cursor_execute', collect)
        assert len(statements) == 1


async def test_schedule_period_blocks_first_closed_month_and_ignores_deleted(pg_session_factory):
    async with pg_session_factory() as session:
        user = User(username='gestor_sintetico', name='Gestor Sintético', role=UserRole.MAINTAINER,
                    password_hash=get_password_hash('senha-sintetica-123'))
        session.add(user)
        await session.flush()
        session.add_all([
            PayrollClosure(year=2024, month=11, is_closed=True, closed_by_user_id=user.id),
            PayrollClosure(year=2024, month=6, is_closed=True, closed_by_user_id=user.id),
            PayrollClosure(year=2024, month=3, is_closed=True, closed_by_user_id=user.id,
                           deleted_at=datetime.fromisoformat('2024-04-01T00:00:00-03:00')),
        ])
        await session.commit()
        service = UserWorkScheduleService(session)
        with pytest.raises(SchedulePayrollClosedError, match='06/2024'):
            await service.check_payroll_closure(session, date(2020, 1, 1), date(2025, 12, 31))
        await service.check_payroll_closure(session, date(2024, 3, 1), date(2024, 3, 31))
