"""Opt-in edge client: separate consent, keyring, and safe monotonic offline behavior."""

# implementation-10042026-Maurice
from __future__ import annotations
from dataclasses import dataclass
import base64, json, logging, platform, subprocess, time
from typing import Any, Callable
from platform_api.observability import traced
from platform_api.privacy import redact_metadata
logger = logging.getLogger("control_plane.edge")

class MemoryKeyring:
    def __init__(self) -> None: self._values: dict[str, str] = {}
    @traced
    def get(self, name: str) -> str | None: return self._values.get(name)
    @traced
    def set(self, name: str, value: str) -> None: self._values[name] = value

class OSKeyring:
    """macOS Keychain/Linux Secret Service adapter with explicit ephemeral fallback."""
    def __init__(self, *, allow_ephemeral: bool = False) -> None:
        self.backend = "darwin-keychain" if platform.system().lower() == "darwin" else "linux-secret-service" if platform.system().lower() == "linux" else "none"
        self.fallback = MemoryKeyring() if allow_ephemeral else None
    def get(self, name: str) -> str | None:
        try:
            if self.backend == "darwin-keychain": return subprocess.check_output(["security", "find-generic-password", "-s", name, "-w"], stderr=subprocess.DEVNULL, text=True).strip()
            if self.backend == "linux-secret-service":
                import keyring; return keyring.get_password("voice-command", name)
        except Exception: pass
        return self.fallback.get(name) if self.fallback else None
    def set(self, name: str, value: str) -> None:
        try:
            if self.backend == "darwin-keychain": subprocess.run(["security", "add-generic-password", "-U", "-s", name, "-w", value], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); return
            if self.backend == "linux-secret-service":
                import keyring; keyring.set_password("voice-command", name, value); return
        except Exception: pass
        if self.fallback: self.fallback.set(name, value)

@dataclass
class Consent:
    privacy: bool = False
    telemetry: bool = False

class EdgeControlPlane:
    def __init__(self, *, transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None, keyring: Any | None = None, consent: Consent | None = None, offline: bool = True) -> None:
        self.transport, self.keyring, self.consent, self.offline = transport, keyring or OSKeyring(allow_ephemeral=True), consent or Consent(), offline
        self._cached: dict[str, Any] | None = None; self._cache_expiry = 0.0  # expires after bounded offline grace

    @traced
    def fetch_config(self, device_id: str) -> dict[str, Any] | None:
        if not self.consent.privacy: return self._cached
        try:
            if self.offline or not self.transport: raise TimeoutError("offline")
            result = self.transport("/v1/devices/" + device_id + "/config", {})
            if not isinstance(result, dict) or not result.get("signature") or int(result.get("version", 0)) < int((self._cached or {}).get("version", 0)): raise ValueError("unverified config")
            self._cached, self._cache_expiry = result, time.monotonic() + 86400; return result
        except (ConnectionError, TimeoutError, ValueError):
            if self._cached and time.monotonic() < self._cache_expiry: return self._cached
            # Safe defaults keep the edge available without pretending to have verified data.
            return {"version": 0, "values": {}, "signature": "", "source": "safe-default"}

    @traced
    def export_telemetry(self, metadata: dict[str, Any]) -> bool:
        if self.offline or not self.transport or not self.consent.telemetry: return False
        try:
            result = self.transport("/v1/telemetry", redact_metadata(metadata)); return bool(result is not None and (not isinstance(result, dict) or result.get("status", "ok") in {"ok", "accepted"}))
        except (ConnectionError, TimeoutError): return False
