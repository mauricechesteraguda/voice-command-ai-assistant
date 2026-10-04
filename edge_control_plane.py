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
    def __init__(self, *, transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None, keyring: Any | None = None, pinned_public_key: bytes | str | None = None, consent: Consent | None = None, offline: bool = True) -> None:
        self.transport, self.keyring, self.consent, self.offline = transport, keyring or OSKeyring(allow_ephemeral=False), consent or Consent(), offline
        self.pinned_public_key = pinned_public_key or (keyring.get("control-plane-pinned-public-key") if keyring else None)
        self._cached: dict[str, Any] | None = None; self._cache_expiry = 0.0  # expires after bounded offline grace

    @traced
    def fetch_config(self, device_id: str) -> dict[str, Any] | None:
        if not self.consent.privacy: return self._cached
        try:
            if self.offline or not self.transport: raise TimeoutError("offline")
            result = self.transport("/v1/devices/" + device_id + "/config", {})
            if not self._verify_config(result, device_id): raise ValueError("unverified config")
            self._cached, self._cache_expiry = result, time.monotonic() + 86400; return result
        except (ConnectionError, TimeoutError, ValueError):
            if self._cached and time.monotonic() < self._cache_expiry: return self._cached
            # Safe defaults keep the edge available without pretending to have verified data.
            return {"version": 0, "values": {}, "signature": "", "source": "safe-default"}

    @traced
    def _verify_config(self, result: Any, device_id: str) -> bool:
        """Verify a canonical Ed25519 envelope against the pinned public key."""
        if not isinstance(result, dict) or not result.get("signature") or not self.pinned_public_key:
            return False
        version = int(result.get("version", 0)); previous = int((self._cached or {}).get("version", 0))
        expires = result.get("expires_at", result.get("expiresAt"))
        if version < previous or expires is None or float(expires) <= time.time(): return False
        payload = {"version": version, "values": result.get("values", {}), "cohort": result.get("cohort", "default"), "device_id": device_id, "expires_at": expires}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            key = self.pinned_public_key
            if isinstance(key, str): key = key.encode()
            if isinstance(key, bytes) and key.startswith(b"-----BEGIN"):
                from cryptography.hazmat.primitives import serialization
                public = serialization.load_pem_public_key(key)
            else:
                raw = base64.urlsafe_b64decode(key + b"=" * (-len(key) % 4)) if isinstance(key, bytes) else base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
                public = Ed25519PublicKey.from_public_bytes(raw)
            public.verify(base64.urlsafe_b64decode(str(result["signature"]) + "=" * (-len(str(result["signature"])) % 4)), body)
            return True
        except Exception:
            logger.warning('{"event":"edge.config.reject","reason":"signature"}')
            return False

    @traced
    def export_telemetry(self, metadata: dict[str, Any]) -> bool:
        if self.offline or not self.transport or not self.consent.telemetry: return False
        try:
            result = self.transport("/v1/telemetry", redact_metadata(metadata)); return bool(result is not None and (not isinstance(result, dict) or result.get("status", "ok") in {"ok", "accepted"}))
        except (ConnectionError, TimeoutError): return False
