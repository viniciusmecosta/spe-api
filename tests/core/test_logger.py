import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.logger import (
    CleanFormatter,
    DailyRotatingFileHandler,
    get_log_path,
    setup_logging,
)


def test_clean_formatter():
    formatter = CleanFormatter("%(levelname)s: %(message)s")
    record = logging.LogRecord("test", logging.WARNING, "path", 1, "msg", (), None)
    formatted = formatter.format(record)
    assert "WARN" in formatted
    assert record.levelname == "WARNING"


def test_daily_rotating_file_handler(tmp_path):
    log_dir = str(tmp_path / "logs")
    handler = DailyRotatingFileHandler(log_dir=log_dir, backup_count=1)

    logger = logging.getLogger("test_daily_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info("Test log message 1")

    if os.path.exists(handler.baseFilename):
        os.remove(handler.baseFilename)
    handler._check_and_reopen_stream_if_deleted()

    handler.last_check = time.time() - 10
    logger.info("Test log message 2")

    handler.next_rollover = time.time() - 1
    logger.info("Test log message 3 after rollover")

    old_date = (datetime.now(ZoneInfo(settings.TIMEZONE)) - timedelta(days=10)).strftime("%d%m%Y")
    old_file_dir = os.path.join(log_dir, "2020", "01")
    os.makedirs(old_file_dir, exist_ok=True)
    old_file_path = os.path.join(old_file_dir, f"{old_date}.log")
    with open(old_file_path, "w") as f:
        f.write("old log")

    handler._cleanup_old_logs()
    handler.backup_count = 0
    handler._cleanup_old_logs()

    handler.close()


def test_setup_logging():
    setup_logging()
