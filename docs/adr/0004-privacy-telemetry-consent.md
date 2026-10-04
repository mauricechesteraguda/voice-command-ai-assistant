# ADR 0004: Separate privacy consent from telemetry consent

## Status
Accepted

## Decision
Privacy/data-sharing consent and operational telemetry consent are independent, revocable decisions. Offline operation and consent denial are valid states. Metadata is allowlisted and redacted before export; conversation content, audio, tokens, and credentials are never telemetry by default.

## Rationale
Operational visibility must not silently authorize data sharing, and users need a useful offline mode when either consent is absent.
