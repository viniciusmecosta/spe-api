from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.features.daily_summaries.daily_summary_reprocess_schemas import DailySummaryReprocessRequest
from app.features.daily_summaries.daily_summary_reprocess_service import DailySummaryReprocessService
from app.features.users.user_models import User
from app.main import app
from app.shared import deps
from app.shared.enums import UserRole


@pytest.fixture(autouse=True)
def mock_enqueue(mocker):
    return mocker.patch('app.features.daily_summaries.daily_summary_reprocess_service.enqueue',
                        new_callable=AsyncMock, return_value=MagicMock(id=42))


@pytest.mark.asyncio
async def test_reprocess_selected_users_and_days(mocker):
    db = MagicMock()
    db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [1, 2]))
    service = DailySummaryReprocessService(db)
    payroll = mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.payroll_service.async_validate_period_open",
        new_callable=AsyncMock,
    )
    audit = mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.audit_service.async_log_change",
        new_callable=AsyncMock,
    )
    background = MagicMock()
    request = DailySummaryReprocessRequest(
        start_date=date(2026, 12, 31), end_date=date(2027, 1, 2), user_ids=[2, 1, 2]
    )

    result = await service.start(request, operator_id=9)

    assert result["status"] == "success"
    assert payroll.await_count == 2
    background.add_task.assert_not_called()
    assert audit.await_args.kwargs["entity"] == "DAILY_SUMMARIES"


@pytest.mark.asyncio
async def test_reprocess_all_users_and_invalid_requests(mocker):
    db = MagicMock()
    db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [1, 3]))
    service = DailySummaryReprocessService(db)
    mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.payroll_service.async_validate_period_open",
        new_callable=AsyncMock,
    )
    mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.audit_service.async_log_change",
        new_callable=AsyncMock,
    )
    background = MagicMock()

    await service.start(
        DailySummaryReprocessRequest(start_date=date(2026, 8, 1), end_date=date(2026, 8, 2)),
        operator_id=9,
    )
    background.add_task.assert_not_called()

    invalid_date_request = DailySummaryReprocessRequest(
        start_date=date(2026, 8, 2), end_date=date(2026, 8, 1)
    )
    with pytest.raises(HTTPException) as invalid_dates:
        await service.start(invalid_date_request, operator_id=9)
    assert invalid_dates.value.status_code == 400

    missing_user_request = DailySummaryReprocessRequest(
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 2), user_ids=[1, 2]
    )
    with pytest.raises(HTTPException) as missing_user:
        await service.start(missing_user_request, operator_id=9)
    assert missing_user.value.status_code == 404


@pytest.mark.asyncio
async def test_closed_period_is_rejected_before_scheduling(mocker):
    db = MagicMock()
    db.scalars = AsyncMock()
    service = DailySummaryReprocessService(db)
    payroll = mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.payroll_service.async_validate_period_open",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=409, detail="Folha fechada"),
    )
    background = MagicMock()

    request = DailySummaryReprocessRequest(
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 2)
    )
    with pytest.raises(HTTPException) as closed:
        await service.start(request, operator_id=9)
    assert closed.value.status_code == 409
    payroll.assert_awaited_once()
    db.scalars.assert_not_awaited()
    background.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_reprocess_runs_every_selected_user_day(mocker):
    recalculate = mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.recalculate_changed_days",
        new_callable=AsyncMock,
        return_value=True,
    )
    service = DailySummaryReprocessService()
    await service._run([1, 2], date(2026, 8, 1), date(2026, 8, 2))
    assert recalculate.await_count == 4
    assert {call.args[0].pop() for call in recalculate.await_args_list} == {
        (1, date(2026, 8, 1)),
        (1, date(2026, 8, 2)),
        (2, date(2026, 8, 1)),
        (2, date(2026, 8, 2)),
    }


def test_reprocess_endpoint_requires_maintainer(mocker):
    mocker.patch('app.core.lifespan.trusted_time_service.sync_ntp_with_backoff_async', new_callable=AsyncMock, return_value=True)
    user = User(id=9, role=UserRole.MAINTAINER, is_active=True)
    app.dependency_overrides[deps.get_current_maintainer] = lambda: user
    start = mocker.patch.object(
        DailySummaryReprocessService, "start", new_callable=AsyncMock,
        return_value={"status": "success", "message": "iniciado", "job_id": "1"},
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/daily-summaries/admin/reprocess",
                json={"start_date": "2026-08-01", "end_date": "2026-08-02"},
            )
        assert response.status_code == 200
        assert start.await_args.args[1] == 9
    finally:
        app.dependency_overrides.clear()


def test_reprocess_endpoint_rejects_employee(mocker):
    mocker.patch('app.core.lifespan.trusted_time_service.sync_ntp_with_backoff_async', new_callable=AsyncMock, return_value=True)
    user = User(id=9, role=UserRole.EMPLOYEE, is_active=True)
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/daily-summaries/admin/reprocess",
                json={"start_date": "2026-08-01", "end_date": "2026-08-02"},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reprocess_limits_run_failures_and_process_job(mocker, monkeypatch):
    from app.core.config import settings
    from app.features.daily_summaries.daily_summary_reprocess_service import process_reprocess_job

    db = MagicMock()
    db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [1, 2, 3]))
    service = DailySummaryReprocessService(db)
    mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.payroll_service.async_validate_period_open",
        new_callable=AsyncMock,
    )

    monkeypatch.setattr(settings, "REPROCESS_MAX_DAYS", 2)
    req_days = DailySummaryReprocessRequest(start_date=date(2026, 8, 1), end_date=date(2026, 8, 5))
    with pytest.raises(HTTPException) as exc_days:
        await service.start(req_days, 1)
    assert exc_days.value.status_code == 422

    monkeypatch.setattr(settings, "REPROCESS_MAX_DAYS", 366)
    monkeypatch.setattr(settings, "REPROCESS_MAX_ITEMS", 2)
    req_items = DailySummaryReprocessRequest(start_date=date(2026, 8, 1), end_date=date(2026, 8, 2))
    with pytest.raises(HTTPException) as exc_items:
        await service.start(req_items, 1)
    assert exc_items.value.status_code == 422

    mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.recalculate_changed_days",
        new_callable=AsyncMock,
        return_value=False,
    )
    await service._run([1], date(2026, 8, 1), date(2026, 8, 1))

    cp = mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.checkpoint",
        new_callable=AsyncMock,
        return_value=True,
    )
    recalc = mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.recalculate_changed_days",
        new_callable=AsyncMock,
        side_effect=[True, False],
    )
    job = {
        "payload": {"start_date": "2026-08-01", "end_date": "2026-08-02", "user_ids": [1]},
        "result": {},
    }
    await process_reprocess_job(job)
    assert recalc.await_count == 2
    assert cp.await_args_list[-1].args[1] == "PARTIAL"

    recalc.side_effect = [False]
    job_retry = {
        "payload": {
            "start_date": "2026-08-01",
            "end_date": "2026-08-01",
            "user_ids": [1],
            "retry_items": [{"user_id": 1, "date": "2026-08-01"}],
        },
        "result": {},
    }
    await process_reprocess_job(job_retry)
    assert cp.await_args_list[-1].args[1] == "FAILED"

    cp.return_value = False
    recalc.side_effect = [True]
    job_abort = {
        "payload": {"start_date": "2026-08-01", "end_date": "2026-08-01", "user_ids": [1]},
        "result": {},
    }
    await process_reprocess_job(job_abort)
