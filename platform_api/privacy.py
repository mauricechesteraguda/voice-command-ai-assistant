"""Allowlist and redaction rules for telemetry and audit metadata."""

# implementation-10042026-Maurice
from __future__ import annotations
from typing import Any
from .observability import traced

ALLOWED_METADATA = frozenset({"event", "status", "version", "platform", "result", "role", "operation"})
FORBIDDEN_CONTENT = frozenset({"audio", "transcript", "prompt", "generated_text", "ip", "hostname", "secret", "token"})


@traced
def redact_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    """Keep only approved, scalar operational metadata."""
    if not metadata:
        return {}
    return {key: str(value)[:128] for key, value in metadata.items() if key in ALLOWED_METADATA and key not in FORBIDDEN_CONTENT}
