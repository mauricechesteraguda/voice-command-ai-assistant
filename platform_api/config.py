"""Signed monotonic configurations, cohorts, and device overrides."""

# implementation-10042026-Maurice
from __future__ import annotations
import hashlib, hmac, json
from dataclasses import dataclass, field
from typing import Any
from .observability import traced

@dataclass(frozen=True)
class SignedConfig:
    version: int; values: dict[str, Any]; signature: str; cohort: str = "default"; device_id: str | None = None

class ConfigStore:
    def __init__(self, signing_key: bytes | str) -> None:
        self.key = signing_key.encode() if isinstance(signing_key, str) else signing_key; self.current: SignedConfig | None = None; self.overrides: dict[str, dict[str, Any]] = {}

    @traced
    def publish(self, values: dict[str, Any], *, version: int, cohort: str = "default") -> SignedConfig:
        if self.current and version <= self.current.version: raise ValueError("configuration version must increase")
        body = json.dumps({"version": version, "values": values, "cohort": cohort}, sort_keys=True, separators=(",", ":")); signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        self.current = SignedConfig(version, dict(values), signature, cohort); return self.current

    @traced
    def verify(self, config: SignedConfig) -> bool:
        payload = {"version": config.version, "values": config.values, "cohort": config.cohort}
        if config.device_id is not None: payload["device_id"] = config.device_id
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")); return hmac.compare_digest(config.signature, hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest())

    @traced
    def set_device_override(self, device_id: str, values: dict[str, Any]) -> None:
        self.overrides[device_id] = dict(values)

    @traced
    def for_device(self, device_id: str) -> SignedConfig | None:
        if self.current is None: return None
        values = dict(self.current.values); values.update(self.overrides.get(device_id, {}))
        body = json.dumps({"version": self.current.version, "values": values, "cohort": self.current.cohort, "device_id": device_id}, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        return SignedConfig(self.current.version, values, signature, self.current.cohort, device_id)
