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
    def __init__(self, signing_key: bytes | str, *, repository: Any | None = None) -> None:
        self.key = signing_key.encode() if isinstance(signing_key, str) else signing_key; self.repository = repository; self.current: SignedConfig | None = None; self.overrides: dict[str, dict[str, Any]] = {}
        if repository:
            record = repository.latest_configuration()
            if record: self.current = SignedConfig(record["version"], dict(record["values"]), record["signature"], record["cohort"])

    @traced
    def publish(self, values: dict[str, Any], *, version: int, cohort: str = "default") -> SignedConfig:
        if self.current and version <= self.current.version: raise ValueError("configuration version must increase")
        body = json.dumps({"version": version, "values": values, "cohort": cohort}, sort_keys=True, separators=(",", ":")); signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        self.current = SignedConfig(version, dict(values), signature, cohort)
        if self.repository: self.repository.save_configuration({"version": version, "values": dict(values), "cohort": cohort, "signature": signature})
        return self.current

    @traced
    def verify(self, config: SignedConfig) -> bool:
        payload = {"version": config.version, "values": config.values, "cohort": config.cohort}
        if config.device_id is not None: payload["device_id"] = config.device_id
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")); return hmac.compare_digest(config.signature, hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest())

    @traced
    def set_device_override(self, device_id: str, values: dict[str, Any]) -> None:
        self.overrides[device_id] = dict(values)
        if self.repository: self.repository.save_override(device_id, values)

    @traced
    def for_device(self, device_id: str) -> SignedConfig | None:
        if self.current is None: return None
        values = dict(self.current.values); values.update(self.overrides.get(device_id, self.repository.get_override(device_id) if self.repository else {}))
        body = json.dumps({"version": self.current.version, "values": values, "cohort": self.current.cohort, "device_id": device_id}, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        return SignedConfig(self.current.version, values, signature, self.current.cohort, device_id)
