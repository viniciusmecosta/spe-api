import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()
_sync_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daily-summary")
_dispatch_loop: asyncio.AbstractEventLoop | None = None


def bind_dispatch_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _dispatch_loop
    _dispatch_loop = loop


async def recalculate_changed_days(
    days: set[tuple[int, date]],
    reset_excess_days: set[tuple[int, date]] | None = None,
) -> None:
    from app.features.daily_summaries.recalculation_service import (
        daily_summary_recalculation_service,
    )

    reset_days = reset_excess_days or set()
    for user_id, day in sorted(days, key=lambda item: (item[1], item[0])):
        reset = (user_id, day) in reset_days
        for attempt in range(3):
            try:
                await daily_summary_recalculation_service.recalculate_day(
                    user_id, day, reset_excess=reset
                )
                break
            except Exception:
                logger.exception(
                    "Daily summary recalculation failed for user %s on %s", user_id, day
                )
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)


def schedule_days(
    days: set[tuple[int, date]],
    reset_excess_days: set[tuple[int, date]] | None = None,
) -> None:
    if not days:
        return
    reset_days = reset_excess_days or set()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        if _dispatch_loop is not None and _dispatch_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                recalculate_changed_days(days, reset_days), _dispatch_loop
            )
            return
        _sync_executor.submit(asyncio.run, recalculate_changed_days(days, reset_days))
        return
    task = loop.create_task(recalculate_changed_days(days, reset_days))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _after_commit(session: Session) -> None:
    days = session.info.pop("daily_summary_changed_days", set())
    reset_excess_days = session.info.pop("daily_summary_reset_excess_days", set())
    schedule_days(days, reset_excess_days)


def _after_rollback(session: Session) -> None:
    session.info.pop("daily_summary_changed_days", None)
    session.info.pop("daily_summary_reset_excess_days", None)


def register_daily_summary_dispatch() -> None:
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
