from __future__ import annotations

import logging
from typing import cast

import structlog
from structlog.stdlib import BoundLogger


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(message)s",
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger() -> BoundLogger:
    return cast(BoundLogger, structlog.get_logger())


def bind_log_context(**kwargs: str) -> None:
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_log_context() -> None:
    structlog.contextvars.clear_contextvars()
