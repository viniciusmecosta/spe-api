from datetime import date

import pytest

from app.features.users.user_models import User
from app.shared.enums import UserRole

pytestmark = pytest.mark.asyncio


async def test_bulk_schedule_preserves_disabled_excess_when_omitted(pg_session_factory):
    from app.features.users.user_models import UserWorkScheduleConfig
    from app.features.users.user_schemas import BulkWorkScheduleCreate
    from app.features.users.user_work_schedule_service import UserWorkScheduleService
    async with pg_session_factory() as session:
        user = User(username='employee', name='Funcionário', role=UserRole.EMPLOYEE)
        session.add(user)
        await session.flush()
        schedule = UserWorkScheduleConfig(user_id=user.id, day_of_week=0, daily_hours=8,
            valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 31), is_daily_excess_enabled=False)
        session.add(schedule)
        await session.commit()
        service = UserWorkScheduleService(session)
        group = await service.get_bulk_schedule(valid_from=schedule.valid_from, valid_until=schedule.valid_until)
        assert group['users'][0]['schedules'][0]['is_daily_excess_enabled'] is False
        data = BulkWorkScheduleCreate(valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 31),
            users=[{'user_id': user.id, 'schedules': [{'day_of_week': 0, 'daily_hours': 8,
                                                   'entry_1': '08:00', 'exit_1': '16:00'}]}])
        await service.update_bulk_schedules(old_valid_from=schedule.valid_from, old_valid_until=schedule.valid_until,
                                           bulk_data=data, current_user_id=user.id)
        await session.refresh(schedule)
        assert schedule.is_daily_excess_enabled is False
