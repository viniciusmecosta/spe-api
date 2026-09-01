from fastapi import FastAPI
import pytest
from app.core.config import settings
from app.core.lifespan import lifespan, scheduler


@pytest.mark.asyncio
async def test_lifespan_default():
    app = FastAPI()
    async with lifespan(app):
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert "daily_excess_check" in job_ids
        assert "tolerance_entries_check" not in job_ids


@pytest.mark.asyncio
async def test_lifespan_exportador(monkeypatch):
    monkeypatch.setattr(settings, "OPERATION_MODE", "EXPORTADOR")
    app = FastAPI()
    async with lifespan(app):
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert "daily_excess_check" in job_ids
        assert "tolerance_entries_check" not in job_ids
        assert "hourly_sync_db" in job_ids

