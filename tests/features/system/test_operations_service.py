from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.features.system.operations_service import OperationsService
from app.features.system.system_models import BackgroundJob, RoutineLog


@pytest.mark.asyncio
async def test_operations_service_readiness_and_snapshot():
    head_rev = OperationsService.expected_revision()
    assert isinstance(head_rev, str)

    db = MagicMock()
    db.execute = AsyncMock()
    scalars_rev = MagicMock()
    scalars_rev.all.return_value = [head_rev]
    db.scalars = AsyncMock(return_value=scalars_rev)

    service = OperationsService(db)
    ready = await service.readiness()
    assert ready["status"] == "ok"

    scalars_wrong = MagicMock()
    scalars_wrong.all.return_value = ["000_wrong"]
    db.scalars = AsyncMock(return_value=scalars_wrong)
    with pytest.raises(HTTPException) as exc_schema:
        await service.readiness()
    assert exc_schema.value.status_code == 503

    db.execute = AsyncMock(side_effect=SQLAlchemyError("down"))
    with pytest.raises(HTTPException) as exc_db:
        await service.readiness()
    assert exc_db.value.status_code == 503

    counts_res = MagicMock()
    counts_res.all.return_value = [("NOTIFICATION", "SUCCESS", 3)]
    db.execute = AsyncMock(side_effect=[MagicMock(), counts_res])

    now = datetime(2026, 8, 14, 12, 0, 0)
    log1 = RoutineLog(
        routine_type="EMAIL_DAILY_BACKUP",
        status="SUCCESS",
        execution_time=now,
        target_date=date(2026, 8, 13),
        details="ok",
    )
    log2 = RoutineLog(
        routine_type="EMAIL_DAILY_BACKUP",
        status="FAILED",
        execution_time=now,
        target_date=date(2026, 8, 12),
        details="old",
    )
    logs_scalars = MagicMock()
    logs_scalars.all.return_value = [log1, log2]

    job1 = BackgroundJob(
        id=1,
        kind="NOTIFICATION",
        status="SUCCESS",
        payload={"routine_type": "EMAIL_DAILY_BACKUP"},
        result={"summary": {"parts": 1}},
        created_at=now,
    )
    jobs_scalars = MagicMock()
    jobs_scalars.all.return_value = [job1]

    db.scalars = AsyncMock(side_effect=[scalars_rev, logs_scalars, jobs_scalars])
    db.scalar = AsyncMock(return_value=now)

    snap = await service.snapshot()
    assert snap["status"] == "ok"
    assert len(snap["jobs"]) == 1
    assert "EMAIL_DAILY_BACKUP" in snap["routines"]
    assert snap["routines"]["EMAIL_DAILY_BACKUP"]["status"] == "SUCCESS"
    assert len(snap["recent_jobs"]) == 1
