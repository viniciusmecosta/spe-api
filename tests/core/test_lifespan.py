import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from app.core.lifespan import lifespan, scheduler


@pytest.mark.asyncio
async def test_lifespan_default(mocker):
    mock_sync = mocker.patch("app.core.lifespan.trusted_time_service.sync_ntp_with_backoff_async", new_callable=AsyncMock)
    mocker.patch("app.core.lifespan.settings.ENVIRONMENT", "prod")
    app = FastAPI()
    async with lifespan(app):
        await asyncio.sleep(0)
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert "daily_excess_check" not in job_ids
        assert "tolerance_entries_check" not in job_ids
        assert "hourly_ntp_sync" in job_ids
        assert "expired_refresh_tokens" in job_ids
        assert "daily_backup_email" in job_ids
        assert "hourly_backup_telegram" in job_ids
        assert scheduler.get_job("durable_jobs").trigger.interval.total_seconds() == 30
    mock_sync.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_dev_does_not_schedule_backups(mocker):
    async def slow_ntp():
        await asyncio.sleep(10)

    mocker.patch("app.core.lifespan.trusted_time_service.sync_ntp_with_backoff_async", side_effect=slow_ntp)
    mocker.patch("app.core.lifespan.settings.ENVIRONMENT", "dev")
    app = FastAPI()
    async with lifespan(app):
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert "daily_backup_email" not in job_ids
        assert "hourly_backup_telegram" not in job_ids
        assert "hourly_ntp_sync" in job_ids
        assert "expired_refresh_tokens" in job_ids
