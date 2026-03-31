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

    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_048_576, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
        logging.getLogger().addHandler(file_handler)
    except OSError as exc:
        logging.warning(
            "Nao foi possivel criar o handler de arquivo de log (%s): %s", LOG_FILE, exc
        )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def read_log_lines(n: int = 200) -> list[str]:
    from collections import deque

    try:
        with open(LOG_FILE, errors="replace") as fh:
            tail = deque(fh, maxlen=n)
        return [line.rstrip() for line in tail]
    except OSError:
        logging.getLogger(__name__).warning("Nao foi possivel ler o arquivo de log: %s", LOG_FILE)
        return []
