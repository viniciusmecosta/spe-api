import asyncio
from datetime import date

import pytest
from sqlalchemy import func, select

from app.features.users.user_exceptions import BulkScheduleValidationError
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.features.users.user_work_schedule_service import UserWorkScheduleService
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


def schedule_data(user_id):
    return {
        'valid_from': date(2026, 10, 1),
        'valid_until': date(2026, 10, 31),
        'users': [{'user_id': user_id, 'schedules': [{'day_of_week': 0, 'daily_minutes': 480}]}],
    }


async def test_simultaneous_schedule_creation_rejects_overlap(pg_session_factory):
    async with pg_session_factory() as setup:
        user = User(username='concorrencia', name='Funcionário', role=UserRole.EMPLOYEE)
        setup.add(user)
        await setup.commit()
        user_id = user.id

    async with pg_session_factory() as first, pg_session_factory() as second:
        payload = schedule_data(user_id)
        await UserWorkScheduleService(first)._lock_mutations(first)
        waiting = asyncio.create_task(
            UserWorkScheduleService(second).bulk_add_schedules(bulk_data=payload, current_user_id=user_id)
        )
        try:
            await asyncio.sleep(0.1)
            assert not waiting.done()
            await UserWorkScheduleService(first).bulk_add_schedules(bulk_data=payload, current_user_id=user_id)
            await first.commit()
            with pytest.raises(BulkScheduleValidationError):
                await asyncio.wait_for(waiting, timeout=5)
            await second.rollback()
            count = await second.scalar(select(func.count()).select_from(UserWorkScheduleConfig))
            assert count == 1
        finally:
            if not waiting.done():
                waiting.cancel()
                await asyncio.gather(waiting, return_exceptions=True)


@pytest.mark.parametrize('split_users', [False, True])
async def test_duplicate_employee_weekday_in_payload_is_rejected(pg_session_factory, split_users):
    async with pg_session_factory() as session:
        user = User(username='duplicado', name='Funcionário', role=UserRole.EMPLOYEE)
        session.add(user)
        await session.commit()
        payload = schedule_data(user.id)
        if split_users:
            payload['users'].append(payload['users'][0].copy())
        else:
            payload['users'][0]['schedules'].append(payload['users'][0]['schedules'][0].copy())
        with pytest.raises(BulkScheduleValidationError):
            await UserWorkScheduleService(session).bulk_add_schedules(bulk_data=payload, current_user_id=user.id)
        assert await session.scalar(select(func.count()).select_from(UserWorkScheduleConfig)) == 0
