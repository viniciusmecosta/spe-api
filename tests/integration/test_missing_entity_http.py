import pytest
from sqlalchemy import func, select
from test_business_input_http import api

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.devices.device_models import DeviceCredential
from app.features.holidays.holiday_models import Holiday
from app.features.payroll.payroll_models import PayrollClosure
from app.features.printers.printer_models import Printer
from app.features.system.system_models import AuditLog, BackgroundJob
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User

__all__ = ['api']
pytestmark = pytest.mark.asyncio


async def test_missing_entities_do_not_succeed_or_modify_data(api, pg_session_factory):
    models = (User, AdjustmentRequest, TimeRecord, Holiday, Printer, DeviceCredential, PayrollClosure, AuditLog, BackgroundJob)
    async with pg_session_factory() as session:
        before = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    cases = [
        ('GET', '/users/999999', {}),
        ('PUT', '/users/999999', {'json': {'name': 'Nome Sintetico'}}),
        ('GET', '/printers/999999', {}),
        ('PATCH', '/printers/999999', {'json': {'name': 'Impressora Sintetica'}}),
        ('DELETE', '/printers/999999', {}),
        ('PUT', '/device-credentials/999999', {'json': {'name': 'Dispositivo Sintetico'}}),
        ('DELETE', '/device-credentials/999999', {}),
        ('GET', '/payroll/999999/download-report', {}),
        ('GET', '/routine-logs/jobs/999999', {}),
        ('POST', '/routine-logs/jobs/999999/retry', {}),
        ('POST', '/time-records/999999/type-transitions', {}),
        ('PATCH', '/time-records/999999', {'json': {
            'record_datetime': '2026-09-29T08:00:00-03:00',
            'edit_justification': 'Teste sintetico de registro inexistente',
        }}),
        ('DELETE', '/time-records/999999', {'params': {
            'justification': 'Teste sintetico de registro inexistente',
        }}),
        ('GET', '/adjustments/999999/download', {}),
        ('PUT', '/adjustments/999999/review', {'json': {'status': 'APPROVED'}}),
        ('PUT', '/adjustments/999999/review', {'json': {'status': 'REJECTED', 'comment': 'Teste sintetico'}}),
        ('DELETE', '/adjustments/999999', {'params': {'reason': 'Teste sintetico'}}),
        ('PUT', '/adjustments/admin/999999/revert-status', {'json': {
            'status': 'PENDING', 'comment': 'Teste sintetico',
        }}),
    ]
    for method, path, kwargs in cases:
        response = await api.client.request(method, '/api/v1' + path, headers=api.headers, **kwargs)
        assert response.status_code == 404, (method, path, response.status_code)
    holiday_delete = await api.client.delete('/api/v1/holidays/999999', headers=api.headers)
    assert holiday_delete.status_code == 200
    assert holiday_delete.json() == {'status': 'success'}
    timeline = await api.client.get('/api/v1/time-records/999999/timeline', headers=api.headers)
    assert timeline.status_code == 200
    assert timeline.json() == []
    async with pg_session_factory() as session:
        after = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    assert after == before
