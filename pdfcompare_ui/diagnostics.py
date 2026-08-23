"""Small, best-effort diagnostic log for the desktop application."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "pdfcompare"


class _DiagnosticHandler(RotatingFileHandler):
    pass


def configure_file_logging(state_dir: Path) -> Path | None:
    """Write non-fatal GUI diagnostics next to the persisted application state."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in logger.handlers:
        if isinstance(handler, _DiagnosticHandler):
            return Path(handler.baseFilename)

    log_path = state_dir / "pdfcompare.log"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        handler = _DiagnosticHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        return None

    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return log_path


def close_file_logging() -> None:
    """Release log files when the app window is destroyed."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if isinstance(handler, _DiagnosticHandler):
            logger.removeHandler(handler)
            handler.close()
