"""Append-only, privacy-safe administrative audit records."""

# implementation-10042026-Maurice
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from .observability import traced
from .privacy import redact_metadata

@dataclass(frozen=True)
class AuditEvent:
    actor: str; action: str; outcome: str; created_at: datetime; metadata: dict[str, str]

class AuditLog:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc)); self._events: list[AuditEvent] = []

    @traced
    def append(self, actor: str, action: str, outcome: str, metadata: dict[str, Any] | None = None) -> AuditEvent:
        event = AuditEvent(actor[:128], action[:128], outcome[:64], self.clock(), redact_metadata(metadata)); self._events.append(event); return event

    @traced
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    @traced
    def purge(self) -> int:
        cutoff = self.clock() - timedelta(days=365); before = len(self._events); self._events[:] = [event for event in self._events if event.created_at >= cutoff]; return before - len(self._events)
