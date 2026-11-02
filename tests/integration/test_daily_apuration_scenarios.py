from datetime import date

import pytest
from sqlalchemy import select
from test_api_workflows import api

from app.features.daily_summaries.daily_summary_models import DailySummary

__all__ = ['api']
pytestmark = pytest.mark.asyncio

DAY = '2026-09-29'
PERIOD = {'month': 9, 'year': 2026}
NORMAL = [('ENTRY', '08:00'), ('EXIT', '12:00'), ('ENTRY', '13:00'), ('EXIT', '17:00')]


@pytest.mark.parametrize(
    ('punches', 'schedule', 'holiday', 'decision', 'expected'),
    [
        (NORMAL, 'enabled', False, None, (480, 480, 480, 0, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '15:00')], 'enabled', False, None, (420, 420, 480, 0, 0, 60)),
        ([('ENTRY', '08:00')], 'enabled', False, None, (0, 0, 480, 0, 0, 480)),
        ([('ENTRY', '08:00'), ('ENTRY', '09:00'), ('EXIT', '17:00')], 'enabled', False, None, (480, 480, 480, 0, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '17:00')], 'enabled', False, None, (540, 480, 480, 60, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '17:00')], 'enabled', False, 'partial', (540, 510, 480, 60, 30, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '17:00')], 'enabled', False, 'approved', (540, 540, 480, 60, 60, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '17:00')], 'enabled', False, 'rejected', (540, 480, 480, 60, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '12:00'), ('ENTRY', '12:30'), ('EXIT', '16:30')], 'enabled', False, None, (480, 450, 480, 30, 0, 30)),
        ([('ENTRY', '08:00'), ('EXIT', '12:00'), ('ENTRY', '12:30'), ('EXIT', '17:00')], 'enabled', False, None, (510, 480, 480, 30, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '12:00'), ('ENTRY', '13:30'), ('EXIT', '17:30')], 'enabled', False, None, (480, 480, 480, 0, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '17:00')], 'enabled', True, None, (540, 540, 0, 0, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '17:00')], 'disabled', False, None, (540, 540, 480, 0, 0, 0)),
        ([('ENTRY', '08:00'), ('EXIT', '17:00')], 'none', False, None, (540, 540, 0, 0, 0, 0)),
    ],
)
async def test_apuration_scenarios_match_expected_minutes_and_history(
    api, pg_session_factory, punches, schedule, holiday, decision, expected,
):
    user_id = await api.create_employee()
    if schedule != 'none':
        await api.request('POST', '/schedules/bulk', json={
            'valid_from': DAY, 'valid_until': DAY, 'users': [{'user_id': user_id, 'schedules': [{
                'day_of_week': 1, 'daily_hours': 8, 'entry_1': '08:00', 'exit_1': '12:00',
                'entry_2': '13:00', 'exit_2': '17:00', 'is_daily_excess_enabled': schedule == 'enabled',
            }]}],
        })
    if holiday:
        await api.request('POST', '/holidays/', 201, json={'date': DAY, 'name': 'Feriado sintetico'})
    for kind, clock in punches:
        await api.add_punch(user_id, kind, clock)
    if decision:
        adjustments = await api.json('GET', '/adjustments/', params=PERIOD)
        excess = next(item for item in adjustments if item['adjustment_type'] == 'DAILY_EXCESS')
        action = 'reject' if decision == 'rejected' else 'approve'
        payload = {'comment': 'Revisao sintetica'}
        if decision == 'partial':
            payload['approved_amount_hours'] = 0.5
        await api.request('PUT', f"/adjustments/{excess['id']}/{action}", json=payload)
    async with pg_session_factory() as session:
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date.fromisoformat(DAY),
        ))
        assert row is not None
        actual = tuple(float(value) for value in (
            row.worked_minutes, row.accounted_minutes, row.expected_minutes, row.excess_minutes,
            row.authorized_excess_minutes, row.missing_minutes,
        ))
    assert actual == pytest.approx(expected)
    history = await api.json('GET', f'/reports/history/user/{user_id}', params=PERIOD)
    day = next(item for item in history['days'] if item['date'] == DAY)
    assert day['worked_time'] == f'{expected[0] // 60:02d}:{expected[0] % 60:02d}'
    assert day['accounted_time'] == f'{expected[1] // 60:02d}:{expected[1] % 60:02d}'
