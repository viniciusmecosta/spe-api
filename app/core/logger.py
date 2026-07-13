import logging
import logging.config
import os
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

LOG_BASE_DIR = "logs"


def get_log_path(target_date: date) -> str:
    year = target_date.strftime("%Y")
    month = target_date.strftime("%m")
    filename = target_date.strftime("%d%m%Y") + ".log"
    return os.path.join(LOG_BASE_DIR, year, month, filename)


class CleanFormatter(logging.Formatter):
    LEVEL_MAP = {
        "WARNING": "WARN",
        "CRITICAL": "CRIT",
    }

    def format(self, record):
        original_levelname = record.levelname
        record.levelname = self.LEVEL_MAP.get(record.levelname, record.levelname)
        result = super().format(record)
        record.levelname = original_levelname
        return result


class DailyRotatingFileHandler(logging.FileHandler):
    def __init__(self, log_dir, backup_count=60, **kwargs):
        self.log_dir = log_dir
        self.backup_count = backup_count
        self.tz = ZoneInfo(settings.TIMEZONE)
        self.check_interval = 5
        self.last_check = time.time()
        os.makedirs(self.log_dir, exist_ok=True)
        self.baseFilename = self._get_current_filename()
        self._calculate_next_rollover()
        super().__init__(self.baseFilename, **kwargs)

    def _get_current_filename(self):
        now = datetime.now(self.tz)
        log_path = get_log_path(now.date())
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        return os.path.abspath(log_path)

    def _calculate_next_rollover(self):
        now = datetime.now(self.tz)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        self.next_rollover = next_midnight.timestamp()

    def emit(self, record):
        current_time = time.time()
        
        if current_time >= self.next_rollover:
            self._do_rollover()
            self.last_check = current_time
        elif current_time - self.last_check >= self.check_interval:
            self.last_check = current_time
            if self.stream is not None:
                try:
                    if not os.path.exists(self.baseFilename):
                        self.stream.close()
                        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
                        self.stream = self._open()
                except Exception:
                    pass

        super().emit(record)

    def _do_rollover(self):
        self.close()
        self.baseFilename = self._get_current_filename()
        self.stream = self._open()
        self._calculate_next_rollover()
        self._cleanup_old_logs()

    def _cleanup_old_logs(self):
        if self.backup_count <= 0:
            return
        cutoff_date = datetime.now(self.tz) - timedelta(days=self.backup_count)
        for root, dirs, files in os.walk(self.log_dir):
            for filename in files:
                if filename.endswith(".log") and len(filename) == 12:
                    try:
                        date_str = filename[:8]
                        file_date = datetime.strptime(date_str, "%d%m%Y").replace(tzinfo=self.tz)
                        if file_date < cutoff_date:
                            os.remove(os.path.join(root, filename))
                    except (ValueError, OSError):
                        continue
        self._remove_empty_dirs()

    def _remove_empty_dirs(self):
        for root, dirs, files in os.walk(self.log_dir, topdown=False):
            if root == self.log_dir:
                continue
            try:
                if not os.listdir(root):
                    os.rmdir(root)
            except OSError:
                continue


def setup_logging() -> None:
    os.makedirs(LOG_BASE_DIR, exist_ok=True)

    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "default": {
                "()": "app.core.logger.CleanFormatter",
                "format": "%(asctime)s [%(levelname)s] %(message)s",
                "datefmt": "%H:%M:%S"
            }
        },
        "handlers": {
            "file_handler": {
                "()": "app.core.logger.DailyRotatingFileHandler",
                "log_dir": LOG_BASE_DIR,
                "backup_count": 60,
                "encoding": "utf-8",
                "formatter": "default",
                "delay": True
            }
        },
        "loggers": {
            "apscheduler": {
                "handlers": ["file_handler"],
                "level": "ERROR",
                "propagate": False
            },
            "app": {
                "handlers": ["file_handler"],
                "level": "INFO",
                "propagate": False
            }
        },
        "root": {
            "level": "INFO",
            "handlers": ["file_handler"]
        }
    }

    logging.config.dictConfig(logging_config)
