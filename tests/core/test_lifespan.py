from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI

from app.core.lifespan import lifespan, scheduler


@pytest.mark.asyncio
async def test_lifespan_default(mocker):
    mock_sync = mocker.patch("app.core.lifespan.trusted_time_service.sync_ntp_async", new_callable=AsyncMock)
    app = FastAPI()
    async with lifespan(app):
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert "daily_excess_check" not in job_ids
        assert "tolerance_entries_check" not in job_ids
        assert "hourly_ntp_sync" in job_ids
        assert "daily_backup_email" in job_ids
        assert "hourly_backup_telegram" in job_ids
    mock_sync.assert_called_once()

