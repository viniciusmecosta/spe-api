from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.features.system.job_service import JobService
from app.features.system.system_models import BackgroundJob


@pytest.mark.asyncio
async def test_job_service_get_not_found():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    service = JobService(db)
    with pytest.raises(HTTPException) as exc:
        await service.get(999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_job_service_get_success():
    now = datetime(2026, 8, 14, 12, 0, 0)
    job = BackgroundJob(
        id=1,
        kind="NOTIFICATION",
        status="SUCCESS",
        attempts=2,
        created_at=now,
        updated_at=now,
        finished_at=now,
        result={
            "summary": {"parts": 1},
            "failed": [{"id": 10}],
            "parts": [
                {
                    "kind": "email",
                    "status": "SUCCESS",
                    "attempts": 1,
                    "filename": "report.pdf",
                    "detail": "ok",
                }
            ],
        },
    )
    db = MagicMock()
    db.get = AsyncMock(return_value=job)
    service = JobService(db)
    res = await service.get(1)
    assert res["id"] == 1
    assert res["progress"] == {"parts": 1}
    assert res["failures"] == [{"id": 10}]
    assert len(res["parts"]) == 1
    assert res["parts"][0]["filename"] == "report.pdf"


@pytest.mark.asyncio
async def test_job_service_retry_not_found_and_invalid_status():
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    service = JobService(db)
    with pytest.raises(HTTPException) as exc404:
        await service.retry(999)
    assert exc404.value.status_code == 404

    job_running = BackgroundJob(id=2, kind="NOTIFICATION", status="PROCESSING", result={})
    db.scalar = AsyncMock(return_value=job_running)
    with pytest.raises(HTTPException) as exc409:
        await service.retry(2)
    assert exc409.value.status_code == 409


@pytest.mark.asyncio
async def test_job_service_retry_reprocess_and_notification_parts():
    job_reprocess = BackgroundJob(
        id=3,
        kind="REPROCESS",
        status="PARTIAL",
        payload={"user_ids": [1, 2]},
        result={"failed": [{"user_id": 2}]},
        attempts=3,
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=job_reprocess)
    service = JobService(db)
    res_rep = await service.retry(3)
    assert res_rep == {"job_id": "3", "status": "PENDING"}
    assert job_reprocess.payload["retry_items"] == [{"user_id": 2}]
    assert job_reprocess.result == {}
    assert job_reprocess.attempts == 0

    job_uncertain = BackgroundJob(
        id=4,
        kind="NOTIFICATION",
        status="PARTIAL",
        payload={},
        result={"parts": [{"kind": "email", "status": "UNCERTAIN", "attempts": 1}]},
    )
    db.scalar = AsyncMock(return_value=job_uncertain)
    with pytest.raises(HTTPException) as exc_unc:
        await service.retry(4)
    assert exc_unc.value.status_code == 409

    job_notif = BackgroundJob(
        id=5,
        kind="NOTIFICATION",
        status="FAILED",
        payload={},
        result={
            "parts": [
                {"kind": "email", "status": "FAILED", "attempts": 4},
                {"kind": "text", "status": "SUCCESS", "attempts": 1},
            ]
        },
    )
    db.scalar = AsyncMock(return_value=job_notif)
    res_notif = await service.retry(5)
    assert res_notif == {"job_id": "5", "status": "PENDING"}
    assert job_notif.result["parts"][0]["status"] == "PENDING"
    assert job_notif.result["parts"][0]["attempts"] == 0
    assert job_notif.result["parts"][1]["status"] == "SUCCESS"

    job_empty_parts = BackgroundJob(
        id=6,
        kind="NOTIFICATION",
        status="FAILED",
        payload={},
        result={},
    )
    db.scalar = AsyncMock(return_value=job_empty_parts)
    res_empty = await service.retry(6)
    assert res_empty == {"job_id": "6", "status": "PENDING"}
