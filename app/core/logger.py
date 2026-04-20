import logging
import logging.config
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


class DailyRotatingFileHandler(logging.FileHandler):
    def __init__(self, log_dir, backup_count=30, **kwargs):
        self.log_dir = log_dir
        self.backup_count = backup_count
        self.tz = ZoneInfo(settings.TIMEZONE)
        os.makedirs(self.log_dir, exist_ok=True)
        self.baseFilename = self.get_current_filename()
        self.calculate_next_rollover()
        super().__init__(self.baseFilename, **kwargs)

    def get_current_filename(self):
        current_date = datetime.now(self.tz).strftime("%d%m%Y")
        return os.path.abspath(os.path.join(self.log_dir, f"{current_date}.log"))

    def calculate_next_rollover(self):
        now = datetime.now(self.tz)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        self.next_rollover = next_midnight.timestamp()

    def emit(self, record):
        if time.time() >= self.next_rollover:
            self.do_rollover()
        super().emit(record)

    def do_rollover(self):
        self.close()
        self.baseFilename = self.get_current_filename()
        self.stream = self._open()
        self.calculate_next_rollover()
        self.cleanup_old_logs()

    def cleanup_old_logs(self):
        if self.backup_count <= 0:
            return
        cutoff_date = datetime.now(self.tz) - timedelta(days=self.backup_count)
        for filename in os.listdir(self.log_dir):
            if filename.endswith(".log") and len(filename) == 12:
                try:
                    date_str = filename[:8]
                    file_date = datetime.strptime(date_str, "%d%m%Y").replace(tzinfo=self.tz)
                    if file_date < cutoff_date:
                        file_path = os.path.join(self.log_dir, filename)
                        os.remove(file_path)
                except (ValueError, OSError):
                    continue


def setup_logging() -> None:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            }
        },
        "handlers": {
            "file_handler": {
                "()": "app.core.logger.DailyRotatingFileHandler",
                "log_dir": log_dir,
                "backup_count": 30,
                "encoding": "utf-8",
                "formatter": "default",
                "delay": True
            }
        },
        "loggers": {
            "apscheduler": {
                "handlers": ["file_handler"],
                "level": "WARNING",
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