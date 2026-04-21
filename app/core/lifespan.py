from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from app.core.config import settings
from app.services.backup_service import backup_service
from app.services.sync_service import sync_service
from app.services.telegram_service import telegram_service

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tz = ZoneInfo(settings.TIMEZONE)

    trigger_aligned = CronTrigger(minute='0,10,20,30,40,50', timezone=tz)

    scheduler.add_job(backup_service.run_daily_backup_routine, trigger=trigger_aligned, id="daily_backup_email",
                      max_instances=1, coalesce=True)
    scheduler.add_job(telegram_service.execute_hourly_backup, trigger=trigger_aligned, id="hourly_backup_telegram",
                      max_instances=1, coalesce=True)
    scheduler.add_job(telegram_service.send_managerial_report, trigger=trigger_aligned, id="daily_report_telegram",
                      max_instances=1, coalesce=True)

    scheduler.add_job(backup_service.clean_old_logs, trigger=trigger_aligned, id="cleanup_routine_logs",
                      max_instances=1, coalesce=True)

    if settings.OPERATION_MODE == "EXPORTADOR":
        scheduler.add_job(sync_service.send_database_to_consumer, trigger=trigger_aligned, id="hourly_sync_db",
                          max_instances=1, coalesce=True)
        scheduler.add_job(sync_service.check_and_sync_all, trigger=trigger_aligned, id="sync_time_records",
                          max_instances=1, coalesce=True)

    scheduler.start()
    yield
    scheduler.shutdown()
