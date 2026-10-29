import httpx
import pytest
from api_workflow_support import ApiWorkflow, seed_root

pytestmark = pytest.mark.asyncio


async def test_maximum_supported_year_is_accepted_by_input_models():
    from app.features.adjustments.adjustment_schemas import AdjustmentWaiverCreate
    from app.features.daily_summaries.daily_summary_reprocess_schemas import (
        DailySummaryReprocessRequest,
    )
    from app.features.holidays.holiday_schemas import HolidayCreate
    from app.features.time_records.time_record_schemas import TimeRecordCreateAdmin
    from app.features.users.user_schemas import BulkWorkScheduleCreate

    day = '9998-12-31'
    assert HolidayCreate(date=day, name='Feriado').date.isoformat() == day
    assert DailySummaryReprocessRequest(start_date=day, end_date=day).end_date.isoformat() == day
    assert AdjustmentWaiverCreate(user_id=1, target_date=day, amount_hours=1, reason_text='Teste').target_date.isoformat() == day
    assert TimeRecordCreateAdmin(user_id=1, record_type='ENTRY', record_datetime=f'{day}T08:00:00-03:00', edit_justification='Teste').record_datetime.date().isoformat() == day
    assert BulkWorkScheduleCreate(valid_from=day, valid_until=day, users=[]).valid_until.isoformat() == day


async def test_extreme_dates_are_rejected_before_mutation(pg_session_factory):
    from app.main import app

    await seed_root(pg_session_factory)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        api = ApiWorkflow(client)
        api.headers = await api.login('qa_root')
        user_id = await api.create_employee()
        cases = [
            ('/daily-summaries/admin/reprocess', {
                'start_date': '9999-12-31', 'end_date': '9999-12-31',
            }),
            ('/holidays/', {'date': '9999-12-31', 'name': 'Feriado sintético'}),
            ('/adjustments/admin/waive', {
                'user_id': user_id, 'target_date': '9999-12-31',
                'amount_hours': 1, 'reason_text': 'Abono sintético',
            }),
            ('/time-records/admin', {
                'user_id': user_id, 'record_type': 'ENTRY',
                'record_datetime': '9999-12-31T08:00:00-03:00',
                'edit_justification': 'Inclusão sintética',
            }),
            ('/schedules/bulk', {
                'valid_from': '9999-12-31', 'valid_until': '9999-12-31',
                'users': [{'user_id': user_id, 'schedules': [{'day_of_week': 4, 'daily_hours': 8}]}],
            }),
        ]
        for path, payload in cases:
            response = await client.post('/api/v1' + path, headers=api.headers, json=payload)
            assert response.status_code == 422, (path, response.status_code)
