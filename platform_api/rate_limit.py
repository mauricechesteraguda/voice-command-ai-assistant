"""Bounded device and caller-scoped request rate limiting with retry windows."""

# implementation-10042026-Maurice
from collections import defaultdict, deque
import time
from typing import Callable
from .observability import traced

class RateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit, self.window_seconds, self.clock, self._hits = limit, window_seconds, clock, defaultdict(deque)

    @traced
    def check(self, key: str, *, scope: str = "caller") -> tuple[bool, int]:
        try:
            now = self.clock(); hits = self._hits[scope + ":" + key]
            while hits and now - hits[0] >= self.window_seconds: hits.popleft()
            if len(hits) >= self.limit: return False, max(1, min(self.window_seconds, int(self.window_seconds - (now - hits[0]))))
            hits.append(now); return True, 0
        except Exception:
            return False, 1  # bounded retry response when limiter state is unavailable
