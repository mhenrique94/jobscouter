from __future__ import annotations

import datetime
import logging
from logging.handlers import RotatingFileHandler

LOG_FILE: str = "/tmp/jobscouter.log"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
_LOG_DATEFMT = "%H:%M:%S"


class _LocalTimeFormatter(logging.Formatter):
    """Formatter que exibe horário no timezone local do processo.

    O formatter padrão do Python usa time.localtime(), que depende do timezone
    do sistema. Em containers Docker sem TZ configurado, isso resulta em UTC.
    Usar datetime.fromtimestamp().astimezone() garante conversão correta para
    o timezone ativo no processo, respeitando a variável de ambiente TZ.
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        ct = datetime.datetime.fromtimestamp(record.created).astimezone()
        if datefmt:
            return ct.strftime(datefmt)
        return ct.strftime(self.default_time_format)


def _make_formatter() -> _LocalTimeFormatter:
    return _LocalTimeFormatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)


def configure_logging(level: str) -> None:
    formatter = _make_formatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level.upper())
    for existing_handler in list(root.handlers):
        root.removeHandler(existing_handler)
        try:
            existing_handler.close()
        except Exception:
            pass
    root.addHandler(handler)

    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_048_576, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
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
