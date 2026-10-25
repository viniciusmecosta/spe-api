from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.features.system.routine_orchestrator import RoutineOrchestrator
from app.features.system.system_models import BackgroundJob, RoutineLog

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 10, 25, 12, 30, tzinfo=ZoneInfo('America/Fortaleza'))


@pytest.fixture
def scheduled_clock(monkeypatch, mocker):
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'prod')
    monkeypatch.setattr(settings, 'DAILY_REPORT_HOUR', 9)
    monkeypatch.setattr(settings, 'HOURLY_BACKUP_START_HOUR', 6)
    monkeypatch.setattr(settings, 'HOURLY_BACKUP_END_HOUR', 19)
    clock = mocker.patch('app.features.system.routine_orchestrator.datetime')
    clock.now.return_value = NOW


@pytest.mark.parametrize('routine', ['EMAIL_DAILY_BACKUP', 'TELEGRAM_DAILY_REPORT', 'TELEGRAM_HOURLY_BACKUP'])
async def test_imported_success_prevents_repeating_delivered_notification(pg_session_factory, scheduled_clock, routine):
    async with pg_session_factory() as session:
        session.add(RoutineLog(routine_type=routine, status='SUCCESS', target_date=date(2026, 10, 24),
                               execution_time=NOW - timedelta(minutes=5)))
        await session.commit()
    result = await RoutineOrchestrator()._enqueue_routine(routine, scheduled=True)
    assert result is None
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 0


@pytest.mark.parametrize('routine', ['EMAIL_DAILY_BACKUP', 'TELEGRAM_DAILY_REPORT', 'TELEGRAM_HOURLY_BACKUP'])
async def test_failed_or_previous_period_is_queued_once_despite_repeated_cron(pg_session_factory, scheduled_clock, routine):
    async with pg_session_factory() as session:
        session.add_all([
            RoutineLog(routine_type=routine, status='FAILED', target_date=date(2026, 10, 24), execution_time=NOW),
            RoutineLog(routine_type=routine, status='SUCCESS', target_date=date(2026, 10, 23),
                       execution_time=NOW - timedelta(hours=1)),
        ])
        await session.commit()
    orchestrator = RoutineOrchestrator()
    ids = [await orchestrator._enqueue_routine(routine, scheduled=True) for _ in range(6)]
    assert len(set(ids)) == 1
    assert ids[0] is not None
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 1


async def test_manual_delivery_is_available_even_after_scheduled_success(pg_session_factory, scheduled_clock):
    async with pg_session_factory() as session:
        session.add(RoutineLog(routine_type='EMAIL_DAILY_BACKUP', status='SUCCESS',
                               target_date=date(2026, 10, 24), execution_time=NOW))
        await session.commit()
    assert await RoutineOrchestrator().send_manual_backup_email() is not None
