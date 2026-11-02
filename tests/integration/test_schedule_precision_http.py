from datetime import date, timedelta
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select, update
from test_api_workflows import api

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_service import daily_summary_service
from app.features.users.user_models import UserWorkScheduleConfig
from app.shared.enums import AdjustmentStatus, AdjustmentType

__all__ = ['api']
pytestmark = pytest.mark.asyncio


async def test_schedule_minutes_match_reports_excel_and_persisted_reprocessing(api, pg_session_factory):
    user_id = await api.create_employee()
    await api.request('POST', '/schedules/bulk', json={
        'valid_from': '2026-09-15', 'valid_until': '2026-09-30', 'users': [{
            'user_id': user_id, 'schedules': [{'day_of_week': 1, 'daily_hours': 8.02,
                'entry_1': '08:00', 'exit_1': '12:00', 'entry_2': '13:00', 'exit_2': '17:01',
                'is_daily_excess_enabled': True}],
        }],
    })
    days = ('2026-09-15', '2026-09-22', '2026-09-29')
    for day in days:
        for kind, clock in (('ENTRY', '08:00'), ('EXIT', '12:00'), ('ENTRY', '13:00'), ('EXIT', '17:01')):
            await api.request('POST', '/time-records/admin', 201, json={
                'user_id': user_id, 'record_type': kind, 'record_datetime': f'{day}T{clock}:00-03:00',
                'edit_justification': 'Registro sintetico',
            })
    async with pg_session_factory() as session:
        schedule = await session.scalar(select(UserWorkScheduleConfig).where(UserWorkScheduleConfig.user_id == user_id))
        assert schedule.daily_hours == pytest.approx(8 + 1 / 60)
        rows = list((await session.scalars(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date.in_([date.fromisoformat(day) for day in days]),
        ))).all())
        assert len(rows) == 3
        assert all((row.expected_minutes, row.accounted_minutes, row.excess_minutes, row.missing_minutes) ==
                   (481, 481, 0, 0) for row in rows)
        await session.execute(update(DailySummary).where(DailySummary.user_id == user_id,
            DailySummary.apuration_date == date.fromisoformat(days[0])).values(expected_minutes=480.6, accounted_minutes=480.6))
        await session.commit()
    await daily_summary_service.calculate_day(user_id, date.fromisoformat(days[0]), refresh_excess=False, allow_closed=True)
    async with pg_session_factory() as session:
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date.fromisoformat(days[0]),
        ))
        assert (row.expected_minutes, row.accounted_minutes) == (481, 481)
    params = {'year': 2026, 'month': 9}
    report = await api.json('GET', f'/reports/user/{user_id}', params=params)
    assert report['summary']['total_accounted_time'] == '24:03'
    assert report['summary']['total_expected_time'] == '24:03'
    excel = await api.request('GET', '/reports/export/excel', params=params)
    workbook = load_workbook(BytesIO(excel.content), data_only=True)
    sheet = workbook['Colaborador Alfa']
    total = next(row for row in sheet.iter_rows() if row[0].value == 'TOTAIS')
    assert total[22].value == timedelta(hours=24, minutes=3)


async def test_excess_detected_when_legacy_daily_hours_is_zero(api, pg_session_factory):
    user_id = await api.create_employee()
    await api.request('POST', '/schedules/bulk', json={
        'valid_from': '2026-09-01', 'valid_until': '2026-09-30', 'users': [{
            'user_id': user_id, 'schedules': [{'day_of_week': 1, 'daily_hours': 8,
                'entry_1': '08:00', 'exit_1': '16:01', 'is_daily_excess_enabled': True}],
        }],
    })
    async with pg_session_factory() as session:
        await session.execute(update(UserWorkScheduleConfig).where(
            UserWorkScheduleConfig.user_id == user_id).values(daily_hours=0))
        await session.commit()
    await api.add_punch(user_id, 'ENTRY', '08:00')
    await api.add_punch(user_id, 'EXIT', '16:02')
    async with pg_session_factory() as session:
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date(2026, 9, 29),
        ))
        assert (row.expected_minutes, row.worked_minutes, row.accounted_minutes, row.excess_minutes) == (481, 482, 481, 1)
        excess = await session.scalar(select(AdjustmentRequest).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.status == AdjustmentStatus.PENDING, AdjustmentRequest.deleted_at.is_(None),
        ))
        assert excess.amount_hours == pytest.approx(1 / 60, abs=0.0001)


async def test_schedule_and_punch_seconds_do_not_create_false_excess(api, pg_session_factory):
    user_id = await api.create_employee()
    await api.request('POST', '/schedules/bulk', json={
        'valid_from': '2026-09-01', 'valid_until': '2026-09-30', 'users': [{
            'user_id': user_id, 'schedules': [{'day_of_week': 1, 'daily_hours': 8,
                'entry_1': '08:00:59', 'exit_1': '16:01:01', 'is_daily_excess_enabled': True}],
        }],
    })
    for kind, clock in (('ENTRY', '08:00:59'), ('EXIT', '16:01:01')):
        await api.request('POST', '/time-records/admin', 201, json={
            'user_id': user_id, 'record_type': kind, 'record_datetime': f'2026-09-29T{clock}-03:00',
            'edit_justification': 'Registro sintetico',
        })
    async with pg_session_factory() as session:
        row = await session.scalar(select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.apuration_date == date(2026, 9, 29),
        ))
        assert (row.expected_minutes, row.worked_minutes, row.accounted_minutes, row.excess_minutes) == (481, 481, 481, 0)
        excess = await session.scalar(select(AdjustmentRequest.id).where(
            AdjustmentRequest.user_id == user_id, AdjustmentRequest.adjustment_type == AdjustmentType.DAILY_EXCESS,
            AdjustmentRequest.deleted_at.is_(None),
        ))
        assert excess is None
