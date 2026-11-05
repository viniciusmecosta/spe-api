from datetime import date, timedelta
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from test_api_workflows import api

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.shared.daily_excess_service import daily_excess_service
from app.shared.enums import AdjustmentStatus, AdjustmentType

__all__ = ["api"]
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('waiver_values', [(0.5, 1.0), (1.0, 0.5)])
async def test_approved_waivers_accumulate_and_recalculate_excess(api, pg_session_factory, waiver_values):
    user_id = await api.create_employee()
    day = '2026-09-29'
    await api.request('POST', '/schedules/bulk', json={
        'valid_from': '2026-09-01', 'valid_until': '2026-09-30', 'users': [{
            'user_id': user_id, 'schedules': [{'day_of_week': 1, 'daily_minutes': 480,
                'entry_1': '08:00', 'exit_1': '16:00', 'is_daily_excess_enabled': True}],
        }],
    })
    await api.add_punch(user_id, 'ENTRY', '08:00')
    await api.add_punch(user_id, 'EXIT', '15:00')
    created = []
    for amount in waiver_values:
        created.append(await api.json('POST', '/adjustments/admin/waive', 201, json={
            'user_id': user_id, 'target_date': day, 'amount_hours': amount,
            'reason_text': 'Abono sintetico',
        }))
    await api.request('POST', '/adjustments/admin/waive', 400, json={
        'user_id': user_id, 'target_date': day, 'amount_hours': 9,
        'reason_text': 'Limite sintetico',
    })
    history = await api.json('GET', '/reports/history', params={'year': 2026, 'month': 9, 'user_id': user_id})
    daily = next(item for item in history['days'] if item['date'] == day)
    assert daily['abono_hours'] == 1.5
    assert daily['worked_time'] == '08:30'
    assert daily['accounted_time'] == '08:00'
    assert daily['daily_excess']['total_minutes'] == 30
    assert daily['abono_id'] is None
    assert {item['id'] for item in daily['adjustments'] if item['adjustment_type'] == 'WAIVER'} == {
        item['id'] for item in created
    }
    async with pg_session_factory() as session:
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date.fromisoformat(day),
        ))
        assert (row.waiver_minutes, row.worked_minutes, row.accounted_minutes, row.excess_minutes) == (90, 510, 480, 30)
        excess = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.status == AdjustmentStatus.PENDING, AdjustmentRequest.deleted_at.is_(None),
        ))
        assert excess.amount_hours == 0.5
        await daily_excess_service.evaluate_user_day_async(session, user_id, date.fromisoformat(day))
        await session.flush()
        recalculated = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.status == AdjustmentStatus.PENDING, AdjustmentRequest.deleted_at.is_(None),
        ))
        assert recalculated.amount_hours == 0.5
        await session.rollback()
    excel = await api.request('GET', '/reports/export/excel', params={'year': 2026, 'month': 9})
    workbook = load_workbook(BytesIO(excel.content), data_only=True)
    sheet = workbook['Colaborador Alfa']
    excel_day = next(row for row in sheet.iter_rows() if row[0].value == '29/09/26')
    assert excel_day[18].value == timedelta(hours=8, minutes=30)
    assert excel_day[22].value == timedelta(hours=8)
    await api.request('DELETE', f"/adjustments/{created[1]['id']}", params={'reason': 'Exclusao sintetica'})
    history = await api.json('GET', '/reports/history', params={'year': 2026, 'month': 9, 'user_id': user_id})
    daily = next(item for item in history['days'] if item['date'] == day)
    remaining = waiver_values[0]
    remaining_minutes = round(remaining * 60)
    expected_worked = f'{7 + remaining_minutes // 60:02d}:{remaining_minutes % 60:02d}'
    assert (daily['abono_hours'], daily['worked_time'], daily['accounted_time']) == (remaining, expected_worked, expected_worked)
    await api.request('PUT', f"/adjustments/admin/{created[0]['id']}/revert-status", json={
        'status': 'PENDING', 'comment': 'Reversao sintetica',
    })
    history = await api.json('GET', '/reports/history', params={'year': 2026, 'month': 9, 'user_id': user_id})
    daily = next(item for item in history['days'] if item['date'] == day)
    assert (daily['abono_hours'], daily['worked_time'], daily['accounted_time']) == (None, '07:00', '07:00')


async def test_only_active_approved_waivers_count_without_punches(api, pg_session_factory):
    user_id = await api.create_employee()
    day = '2026-09-29'
    await api.request('POST', '/schedules/bulk', json={
        'valid_from': '2026-09-01', 'valid_until': '2026-09-30', 'users': [{
            'user_id': user_id, 'schedules': [{'day_of_week': 1, 'daily_minutes': 480,
                'entry_1': '08:00', 'exit_1': '16:00', 'is_daily_excess_enabled': True}],
        }],
    })
    waivers = []
    for amount in (1, 2, 0.5):
        waivers.append(await api.json('POST', '/adjustments/admin/waive', 201, json={
            'user_id': user_id, 'target_date': day, 'amount_hours': amount,
            'reason_text': 'Abono sintetico',
        }))
    await api.request('PUT', f"/adjustments/admin/{waivers[0]['id']}/revert-status", json={
        'status': 'PENDING', 'comment': 'Revisao sintetica',
    })
    await api.request('PUT', f"/adjustments/{waivers[1]['id']}/review", json={"status": "REJECTED", 'comment': 'Rejeicao sintetica'})
    history = await api.json('GET', '/reports/history', params={'year': 2026, 'month': 9, 'user_id': user_id})
    daily = next(item for item in history['days'] if item['date'] == day)
    assert (daily['abono_hours'], daily['abono_id'], daily['worked_time']) == (0.5, waivers[2]['id'], '00:30')
    async with pg_session_factory() as session:
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date.fromisoformat(day),
        ))
        assert (row.waiver_minutes, row.accounted_minutes, row.missing_minutes) == (30, 30, 450)
        excess = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        ))
        assert excess is None
