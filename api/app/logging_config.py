from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def configure_logging(name_app: str, run_environment: str, path_to_logs: str = "") -> None:
    logger.remove()

    fmt_console = "{time:HH:mm:ss.SSS} | {level} | {module}:{function}:{line} | {message}"
    fmt_file = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {module}:{function}:{line} | {message}"

    if run_environment == "development":
        logger.add(
            sys.stderr,
            format=fmt_console,
            level="DEBUG",
            backtrace=True,
            diagnose=True,
        )
    elif run_environment == "testing":
        logger.add(
            sys.stderr,
            format=fmt_console,
            level="INFO",
            backtrace=True,
            diagnose=True,
        )
        if path_to_logs:
            log_file = Path(path_to_logs) / f"{name_app}.log"
            logger.add(
                str(log_file),
                format=fmt_file,
                level="INFO",
                rotation="3 MB",
                retention=3,
                enqueue=True,
                backtrace=True,
                diagnose=True,
            )
    elif run_environment == "production":
        if path_to_logs:
            log_file = Path(path_to_logs) / f"{name_app}.log"
            logger.add(
                str(log_file),
                format=fmt_file,
                level="INFO",
                rotation="3 MB",
                retention=3,
                enqueue=True,
                backtrace=True,
                diagnose=True,
            )

    def _handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical(
            "Uncaught exception"
        )

    sys.excepthook = _handle_exception
