import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.features.daily_summaries.recalculation_service import (
    daily_summary_recalculation_service,
)


logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()
_sync_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daily-summary")


async def recalculate_changed_days(days: set[tuple[int, date]]) -> None:
    for user_id, day in sorted(days):
        try:
            await daily_summary_recalculation_service.recalculate_day(user_id, day)
        except Exception:
            logger.exception(
                "Daily summary recalculation failed for user %s on %s", user_id, day
            )


async def recover_pending_days() -> None:
    try:
        while await daily_summary_recalculation_service.run_once():
            pass
    except Exception:
        logger.exception("Daily summary startup recovery failed")


def _after_commit(session: Session) -> None:
    days = session.info.pop("daily_summary_changed_days", set())
    if not days:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _sync_executor.submit(asyncio.run, recalculate_changed_days(days))
        return
    task = loop.create_task(recalculate_changed_days(days))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _after_rollback(session: Session) -> None:
    session.info.pop("daily_summary_changed_days", None)


def register_daily_summary_dispatch() -> None:
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
