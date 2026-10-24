from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_service import daily_summary_service
from app.features.holidays.holiday_models import Holiday
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType
from app.shared.time_calculation_service import time_calculation_service


@pytest.mark.asyncio
@pytest.mark.parametrize(('scenario', 'approved'), [('pending', 0), ('rejected', 0), ('partial', .5),
                                                   ('approved', 1), ('waiver', 0), ('holiday', 0), ('legacy', 1)])
async def test_materialized_hours_preserve_gross_and_accounted_contract(pg_session_factory, scenario, approved):
    factory = pg_session_factory
    day = date(2026, 10, 1)
    async with factory() as session:
        user = User(name='Funcionário Sintético', username='contract')
        session.add(user)
        await session.commit()
        schedule = UserWorkScheduleConfig(user_id=user.id, day_of_week=day.weekday(), daily_hours=8,
                                          valid_from=day, valid_until=day)
        session.add(schedule)
        await session.commit()
        end = '14:00' if scenario == 'waiver' else '17:00'
        records = [TimeRecord(user_id=user.id, record_type=kind,
                              record_datetime=datetime.fromisoformat(f'{day}T{hour}:00-03:00'))
                   for kind, hour in ((RecordType.ENTRY, '08:00'), (RecordType.EXIT, end))]
        session.add_all(records)
        if scenario == 'holiday':
            session.add(Holiday(date=day, name='Feriado sintético'))
        await session.commit()
        excess = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user.id, AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS))
        if excess and scenario in ('partial', 'approved', 'rejected'):
            excess.status = AdjustmentStatus.REJECTED if scenario == 'rejected' else AdjustmentStatus.APPROVED
            excess.approved_amount_hours = approved
        if scenario in ('waiver', 'legacy'):
            session.add(AdjustmentRequest(user_id=user.id, target_date=day,
                       adjustment_type=AdjustmentType.WAIVER if scenario == 'waiver' else AdjustmentType.EXTRA_TIME,
                       amount_hours=2 if scenario == 'waiver' else 1, approved_amount_hours=2 if scenario == 'waiver' else 1,
                       status=AdjustmentStatus.APPROVED))
        await session.commit()
    async with factory() as session:
        records = list((await session.scalars(select(TimeRecord))).all())
        adjustments = list((await session.scalars(select(AdjustmentRequest))).all())
        holidays = list((await session.scalars(select(Holiday))).all())
        schedules = list((await session.scalars(select(UserWorkScheduleConfig))).all())
        legacy = time_calculation_service.calculate_period_time(day, day, records, adjustments, holidays, schedules)
        stored = await daily_summary_service.build_period(session, user.id, day, day, records, adjustments, holidays, schedules)
        row = await session.scalar(select(DailySummary))
        assert stored.total_gross_worked_seconds == pytest.approx(legacy.total_gross_worked_seconds)
        assert stored.total_accounted_seconds == pytest.approx(legacy.total_accounted_seconds)
        assert stored.total_waiver_seconds == pytest.approx(legacy.total_waiver_seconds)
        assert stored.final_balance_seconds == pytest.approx(legacy.final_balance_seconds)
        assert float(row.worked_minutes) * 60 == pytest.approx(legacy.total_gross_worked_seconds)
        assert float(row.accounted_minutes) * 60 == pytest.approx(legacy.total_accounted_seconds)
        if scenario in ('pending', 'rejected', 'partial', 'approved'):
            assert float(row.worked_minutes) == 540
            assert float(row.accounted_minutes) == 480 + 60 * approved
