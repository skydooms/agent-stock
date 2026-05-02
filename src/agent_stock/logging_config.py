from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def force_utf8_stdio() -> None:
    """强制 stdout/stderr 使用 UTF-8，避免 Windows cp936 控制台中文乱码."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def setup_logging(level: int = logging.INFO, log_dir: str = ".logs") -> None:
    force_utf8_stdio()
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
