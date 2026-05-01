from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: int = logging.INFO, log_dir: str = ".logs") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    file_handler = RotatingFileHandler(
        f"{log_dir}/agent_stock.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers, format=fmt)
