"""
Logging estruturado simples e compatível com todas as versões de structlog.
"""

import logging
import sys
from config import LOG_LEVEL


def setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        stream=sys.stdout,
    )


class _BoundLogger:
    """Logger simples com interface compatível com structlog."""

    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    def _fmt(self, event: str, **kw) -> str:
        if kw:
            pairs = " ".join(f"{k}={v!r}" for k, v in kw.items())
            return f"{event}  {pairs}"
        return event

    def debug(self, event: str, **kw) -> None:
        self._log.debug(self._fmt(event, **kw))

    def info(self, event: str, **kw) -> None:
        self._log.info(self._fmt(event, **kw))

    def warning(self, event: str, **kw) -> None:
        self._log.warning(self._fmt(event, **kw))

    def error(self, event: str, **kw) -> None:
        self._log.error(self._fmt(event, **kw))


setup_logging()


def get_logger(name: str) -> "_BoundLogger":
    return _BoundLogger(name)
