"""Opt-in edge client: separate consent, keyring, transport, and offline behavior."""

# implementation-10042026-Maurice
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from platform_api.observability import traced
from platform_api.privacy import redact_metadata

class MemoryKeyring:
    def __init__(self) -> None: self._values: dict[str, str] = {}
    @traced
    def get(self, name: str) -> str | None: return self._values.get(name)
    @traced
    def set(self, name: str, value: str) -> None: self._values[name] = value

@dataclass
class Consent:
    privacy: bool = False
    telemetry: bool = False

class EdgeControlPlane:
    def __init__(self, *, transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None, keyring: Any | None = None, consent: Consent | None = None, offline: bool = True) -> None:
        self.transport, self.keyring, self.consent, self.offline = transport, keyring or MemoryKeyring(), consent or Consent(), offline

    @traced
    def fetch_config(self, device_id: str) -> dict[str, Any] | None:
        if self.offline or not self.transport or not self.consent.privacy: return None
        return self.transport("/v1/devices/" + device_id + "/config", {})

    @traced
    def export_telemetry(self, metadata: dict[str, Any]) -> bool:
        if self.offline or not self.transport or not self.consent.telemetry: return False
        self.transport("/v1/telemetry", redact_metadata(metadata)); return True
