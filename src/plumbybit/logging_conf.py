"""Configuracao de logging estruturado + buffer em memoria para o web UI."""
from __future__ import annotations

import logging
import sys
import time
from collections import deque
from threading import Lock
from typing import Any

import structlog

_BUFFER: deque[dict[str, Any]] = deque(maxlen=2000)
_BUF_LOCK = Lock()
_SEQ = 0


def _buffer_processor(_logger, _method, event_dict):
    """structlog processor: guarda cada evento num ring buffer consultavel."""
    global _SEQ
    with _BUF_LOCK:
        _SEQ += 1
        _BUFFER.append({"seq": _SEQ, "ts": time.time(), **{k: _coerce(v) for k, v in event_dict.items()}})
    return event_dict


def _coerce(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def recent_logs(after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    with _BUF_LOCK:
        items = [e for e in _BUFFER if e["seq"] > after_seq]
    return items[-limit:]


def configure(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _buffer_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
