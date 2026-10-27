import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.request_context import request_id
from app.features.system import job_queue
from app.features.system.system_models import BackgroundJob


def _ctx(session):
    class _Manager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

    return _Manager()


@pytest.mark.asyncio
async def test_enqueue_and_submit(mocker):
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.begin_nested = MagicMock(return_value=_ctx(session))

    existing_job = BackgroundJob(id=10, kind="NOTIFICATION", payload={}, result={})
    session.scalar = AsyncMock(return_value=existing_job)
    assert await job_queue.enqueue(session, "NOTIFICATION", {}, key="dup-key") is existing_job

    token = request_id.set("req-123")
    try:
        session.scalar = AsyncMock(return_value=None)
        created = await job_queue.enqueue(session, "NOTIFICATION", {"a": 1}, key="new-key")
        assert created.payload["request_id"] == "req-123"
    finally:
        request_id.reset(token)

    def fail_flush():
        raise IntegrityError("INSERT", {}, Exception("dup"))

    session.flush = AsyncMock(side_effect=fail_flush)
    session.scalar = AsyncMock(side_effect=[None, existing_job])
    recovered = await job_queue.enqueue(session, "NOTIFICATION", {}, key="race-key")
    assert recovered is existing_job

    with pytest.raises(IntegrityError):
        await job_queue.enqueue(session, "NOTIFICATION", {}, key=None)

    session.scalar = AsyncMock(side_effect=[None, None])
    with pytest.raises(IntegrityError):
        await job_queue.enqueue(session, "NOTIFICATION", {}, key="missing-after-conflict")

    mocker.patch("app.features.system.job_queue.get_async_session_context", return_value=_ctx(session))
    mocker.patch("app.features.system.job_queue.enqueue", new_callable=AsyncMock, return_value=existing_job)
    assert await job_queue.submit("NOTIFICATION", {"x": 1}, "k") == 10


@pytest.mark.asyncio
async def test_claim_and_checkpoint(mocker):
    session = MagicMock()
    mocker.patch("app.features.system.job_queue.get_async_session_context", return_value=_ctx(session))

    session.scalar = AsyncMock(return_value=None)
    assert await job_queue.claim() is None

    job_obj = BackgroundJob(id=5, kind="REPROCESS", payload={"target_date": "2026-08-01"}, result={"summary": {"ok": 1}}, attempts=0)
    session.scalar = AsyncMock(return_value=job_obj)
    claimed = await job_queue.claim()
    assert claimed["id"] == 5
    assert claimed["attempts"] == 1
    assert job_obj.status == "PROCESSING"

    res_zero = MagicMock(rowcount=0)
    session.execute = AsyncMock(return_value=res_zero)
    assert await job_queue.checkpoint(claimed, "PROCESSING") is False

    res_one = MagicMock(rowcount=1)
    session.execute = AsyncMock(return_value=res_one)
    session.add = MagicMock()
    assert await job_queue.checkpoint(claimed, "SUCCESS") is True
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_keep_lease_branches(mocker):
    session = MagicMock()
    mocker.patch("app.features.system.job_queue.get_async_session_context", return_value=_ctx(session))
    mocker.patch("app.features.system.job_queue.asyncio.sleep", new_callable=AsyncMock)

    res_ok = MagicMock(rowcount=1)
    res_lost = MagicMock(rowcount=0)
    session.execute = AsyncMock(side_effect=[res_ok, res_lost])
    session.scalar = AsyncMock(return_value=5)

    job = {"id": 5, "token": "tok"}
    await job_queue.keep_lease(job)

    session.execute = AsyncMock(return_value=res_lost)
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="reserva da tarefa"):
        await job_queue.keep_lease(job)


@pytest.mark.asyncio
async def test_execute_and_process_once(mocker):
    mock_reprocess = mocker.patch(
        "app.features.daily_summaries.daily_summary_reprocess_service.process_reprocess_job",
        new_callable=AsyncMock,
    )
    mock_notif = mocker.patch(
        "app.features.system.notification_jobs.process_notification_job",
        new_callable=AsyncMock,
    )

    await job_queue._execute_job({"kind": "REPROCESS"})
    mock_reprocess.assert_awaited_once()

    await job_queue._execute_job({"kind": "NOTIFICATION"})
    mock_notif.assert_awaited_once()

    async def fake_keep_lease(job):
        await asyncio.sleep(3600)

    mocker.patch("app.features.system.job_queue.keep_lease", side_effect=fake_keep_lease)
    await job_queue._process_claimed({"kind": "NOTIFICATION"})

    mocker.patch.object(job_queue.settings, "BACKGROUND_JOBS_ENABLED", False)
    await job_queue.process_once()

    mocker.patch.object(job_queue.settings, "BACKGROUND_JOBS_ENABLED", True)
    mocker.patch("app.features.system.job_queue.claim", new_callable=AsyncMock, return_value=None)
    await job_queue.process_once()

    job_data = {"id": 1, "kind": "NOTIFICATION", "payload": {"request_id": "r1"}, "result": {}, "attempts": 1}
    mocker.patch("app.features.system.job_queue.claim", new_callable=AsyncMock, return_value=job_data)
    mocker.patch("app.features.system.job_queue._process_claimed", new_callable=AsyncMock)
    await job_queue.process_once()

    mocker.patch(
        "app.features.system.job_queue._process_claimed",
        new_callable=AsyncMock,
        side_effect=asyncio.CancelledError(),
    )
    with pytest.raises(asyncio.CancelledError):
        await job_queue.process_once()

    mocker.patch(
        "app.features.system.job_queue._process_claimed",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    )
    mock_cp = mocker.patch("app.features.system.job_queue.checkpoint", new_callable=AsyncMock)
    await job_queue.process_once()
    mock_cp.assert_awaited_once_with(job_data, "RETRY", delay=60)
