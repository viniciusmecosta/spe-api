from contextlib import asynccontextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from app.core.config import settings
from app.features.devices.sync_service import sync_service
from app.features.system.routine_orchestrator import routine_orchestrator
from app.shared.trusted_time_service import trusted_time_service

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo(settings.TIMEZONE)

    trigger_aligned = CronTrigger(minute='0,10,20,30,40,50', timezone=tz)
    trigger_hourly = CronTrigger(minute=0, timezone=tz)

    scheduler.add_job(routine_orchestrator.run_daily_backup_routine_email, trigger=trigger_aligned,
                      id="daily_backup_email",
                      max_instances=1, coalesce=True)
    scheduler.add_job(routine_orchestrator.execute_hourly_backup_telegram, trigger=trigger_aligned,
                      id="hourly_backup_telegram",
                      max_instances=1, coalesce=True)
    scheduler.add_job(routine_orchestrator.send_managerial_report_telegram, trigger=trigger_aligned,
                      id="daily_report_telegram",
                      max_instances=1, coalesce=True)

    scheduler.add_job(routine_orchestrator.clean_old_logs, trigger=trigger_aligned, id="cleanup_routine_logs",
                      max_instances=1, coalesce=True)

    scheduler.add_job(trusted_time_service.sync_ntp_async, trigger=trigger_hourly, id="hourly_ntp_sync",
                      max_instances=1, coalesce=True)

    if settings.OPERATION_MODE == "EXPORTADOR":
        scheduler.add_job(sync_service.send_database_to_consumer, trigger=trigger_aligned, id="hourly_sync_db",
                          max_instances=1, coalesce=True)

    scheduler.start()
    yield
    scheduler.shutdown()
