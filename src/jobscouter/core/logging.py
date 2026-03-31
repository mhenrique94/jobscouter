from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

LOG_FILE = "/tmp/jobscouter.log"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
_LOG_DATEFMT = "%H:%M:%S"


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format=_LOG_FORMAT,
        datefmt=_LOG_DATEFMT,
        force=True,
    )

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_048_576, backupCount=2)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
    logging.getLogger().addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def read_log_lines(n: int = 200) -> list[str]:
    try:
        with open(LOG_FILE) as fh:
            lines = fh.readlines()
        return [line.rstrip() for line in lines[-n:]]
    except FileNotFoundError:
        return []
