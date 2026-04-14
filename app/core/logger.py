import logging
import logging.config
import os

def setup_logging() -> None:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "spe.log")

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
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file,
                "maxBytes": 100 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
                "formatter": "default",
                "delay": True
            }
        },
        "loggers": {
            "apscheduler": {
                "handlers": ["file_handler"],
                "level": "INFO",
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