"""Privacy-safe logs, metrics, and optional tracing ports."""

# implementation-10042026-Maurice
from __future__ import annotations

import functools
import json
import logging
import time
import uuid
from typing import Any, Callable, TypeVar

logger = logging.getLogger("control_plane")
F = TypeVar("F", bound=Callable[..., Any])


def redact(value: Any) -> str:
    """Return a bounded, non-content representation for operational logs."""
    return type(value).__name__ if value is not None else "none"


def traced(fn: F) -> F:
    """Trace lifecycle only; arguments and return values are never recorded."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        correlation_id = uuid.uuid4().hex
        logger.info(json.dumps({"event": "operation.start", "operation": fn.__name__, "correlation_id": correlation_id}, sort_keys=True))
        try:
            result = fn(*args, **kwargs)
            logger.info(json.dumps({"event": "operation.end", "operation": fn.__name__, "correlation_id": correlation_id, "duration_ms": round((time.monotonic() - started) * 1000, 2)}, sort_keys=True))
            return result
        except Exception as exc:
            logger.warning(json.dumps({"event": "operation.error", "operation": fn.__name__, "correlation_id": correlation_id, "error_type": type(exc).__name__}, sort_keys=True))
            raise
    return wrapper  # type: ignore[return-value]


class Metrics:
    """In-memory counters with a deliberately tiny injectable surface."""
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    @traced
    def increment(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    @traced
    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)
